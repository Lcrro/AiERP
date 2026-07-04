# 材料申请 ToolCall 示例

本文用一个最小业务场景说明：Agent Runtime 如何把员工一句话转换成 ERPNext `Material Request` 草稿。

示例假设当前日期为 `2026-06-23`。

## 用户输入

班组长说：

```text
明天城东项目要 100 双帆布手套，送项目仓。
```

这个输入里有几类信息：

| 信息 | 用户原文 | 是否可直接写入 ToolCall |
|---|---|---:|
| 业务意图 | 要物料 / 申请物料 | 否，需要映射为材料申请 |
| 日期 | 明天 | 否，需要 Date Resolver 转成 ISO 日期 |
| 项目 | 城东项目 | 否，需要 Project Resolver 查真实 Project |
| 物料 | 帆布手套 | 否，需要 Item Resolver 查真实 Item |
| 数量 | 100 | 是，但仍需校验为正数 |
| 单位 | 双 | 可用，但需校验是否与物料单位兼容 |
| 仓库 | 项目仓 | 否，需要 Warehouse Resolver 查 ERPNext 仓库全称 |

## 第一步：模型只抽取意图草稿

大模型不要直接生成最终 ToolCall。第一步只输出人话槽位：

```json
{
  "intent": "create_material_request",
  "project_text": "城东项目",
  "warehouse_text": "项目仓",
  "schedule_text": "明天",
  "items": [
    {
      "raw_item_text": "帆布手套",
      "qty": 100,
      "uom_text": "双"
    }
  ]
}
```

这一步允许模型理解人话，但不允许模型编造 `item_code`、`warehouse`、`project`。

## 第二步：Runtime 注入上下文

Runtime 根据当前登录员工和站点配置注入模型不应该猜的上下文：

```json
{
  "current_date": "2026-06-23",
  "erpnext_user": "ma.chao@scen-civil.local",
  "employee_name": "马超",
  "role_profile": "班组长",
  "company": "STEC (Demo)",
  "site_profile": "civil"
}
```

## 第三步：Resolver 查询已有数据

Runtime 调用 Resolver，把人话解析成 ERPNext 里的真实值。

### 日期解析

```json
{
  "slot": "schedule_date",
  "input": "明天",
  "resolver": "DateResolver",
  "status": "resolved",
  "value": "2026-06-24",
  "reason": "当前日期为 2026-06-23，明天解析为 2026-06-24。"
}
```

### 项目解析

```json
{
  "slot": "project",
  "input": "城东项目",
  "resolver": "ProjectResolver",
  "status": "resolved",
  "value": "PROJ-0001",
  "label": "城东道路改造项目",
  "confidence": 0.95,
  "reason": "项目简称命中唯一在建项目。"
}
```

### 仓库解析

```json
{
  "slot": "warehouse",
  "input": "项目仓",
  "resolver": "WarehouseResolver",
  "status": "resolved",
  "value": "SCEN-CIVIL 项目仓 - SD",
  "label": "SCEN-CIVIL 项目仓",
  "confidence": 0.92,
  "reason": "班组长场景下的项目仓简称命中默认项目仓。"
}
```

### 物料解析

```json
{
  "slot": "items[0].item_code",
  "input": "帆布手套",
  "resolver": "ItemResolver",
  "status": "resolved",
  "value": "SAFE-000005",
  "label": "帆布手套",
  "stock_uom": "双",
  "confidence": 0.97,
  "reason": "标准名称和别名精确匹配，单位与用户输入一致。"
}
```

如果物料不唯一，不能强行选择。例如：

```json
{
  "slot": "items[0].item_code",
  "input": "角铁",
  "resolver": "ItemResolver",
  "status": "needs_confirmation",
  "candidates": [
    {"value": "METAL-000007", "label": "角铁 50*50*6", "confidence": 0.86},
    {"value": "METAL-000043", "label": "角钢 40*40*5", "confidence": 0.83}
  ],
  "question": "你要的是 50*50*6 的角铁，还是 40*40*5 的角钢？"
}
```

## 第四步：参数编排层填 ToolCall

Resolver 全部通过后，参数编排层生成候选 ToolCall：

```json
{
  "tool": "erpnext.buying.create_material_request_draft",
  "arguments": {
    "company": "STEC (Demo)",
    "material_request_type": "Purchase",
    "schedule_date": "2026-06-24",
    "items": [
      {
        "item_code": "SAFE-000005",
        "qty": 100,
        "uom": "双",
        "schedule_date": "2026-06-24",
        "warehouse": "SCEN-CIVIL 项目仓 - SD",
        "project": "PROJ-0001",
        "description": "城东道路改造项目班组劳保用品需求"
      }
    ]
  }
}
```

注意：

- `company` 来自 Runtime Context，不让模型猜。
- `material_request_type` 默认 `Purchase`。
- `schedule_date` 来自 Date Resolver。
- `item_code` 来自 Item Resolver。
- `warehouse` 来自 Warehouse Resolver。
- `project` 来自 Project Resolver。
- `qty` 来自模型抽取，但必须校验为大于 0 的数字。
- `uom` 可以来自用户输入，但必须和物料主数据兼容。

## 第五步：Validator / Preflight 校验

执行前至少校验：

| 校验项 | 规则 |
|---|---|
| Tool schema | `items` 必填，且至少 1 行 |
| 数量 | `qty > 0` |
| 日期 | `schedule_date` 必须是 `YYYY-MM-DD` |
| 物料 | `SAFE-000005` 必须存在且未禁用 |
| 仓库 | `SCEN-CIVIL 项目仓 - SD` 必须存在 |
| 项目 | `PROJ-0001` 必须存在 |
| 权限 | 当前班组长 profile 是否允许创建材料申请草稿 |
| 风险 | L3 草稿写入，需要用户确认 |

如果校验通过，但属于写入类动作，Runtime 应先展示确认摘要。

## 第六步：用户确认

给用户看的确认话术应该是业务语言：

```text
我准备创建一张材料申请草稿：

公司：STEC (Demo)
项目：城东道路改造项目
需求日期：2026-06-24
目标仓库：SCEN-CIVIL 项目仓
物料：帆布手套
数量：100 双

确认后我会创建草稿，不会提交审批。
```

确认后，ToolGateway 才允许执行。

## 第七步：ToolGateway 执行

执行路径：

```text
ToolCall
  -> ToolGateway
  -> ERPNextAdapter._buying_create_material_request_draft
  -> ERPNextClient.create_document("Material Request", data)
  -> ERPNext / Frappe API
```

实际写入 ERPNext 的 DocType 数据接近：

```json
{
  "doctype": "Material Request",
  "material_request_type": "Purchase",
  "schedule_date": "2026-06-24",
  "company": "STEC (Demo)",
  "docstatus": 0,
  "items": [
    {
      "item_code": "SAFE-000005",
      "qty": 100,
      "uom": "双",
      "schedule_date": "2026-06-24",
      "warehouse": "SCEN-CIVIL 项目仓 - SD",
      "project": "PROJ-0001",
      "description": "城东道路改造项目班组劳保用品需求"
    }
  ]
}
```

## ERPNext 底层表结构效果

ERPNext 保存后大致会影响：

```text
tabMaterial Request
  name = MAT-MR-....
  material_request_type = Purchase
  schedule_date = 2026-06-24
  company = STEC (Demo)
  docstatus = 0

tabMaterial Request Item
  parent = MAT-MR-....
  parenttype = Material Request
  parentfield = items
  item_code = SAFE-000005
  qty = 100
  uom = 双
  warehouse = SCEN-CIVIL 项目仓 - SD
  project = PROJ-0001
```

这里不要直接 SQL 写库。必须走 Frappe API，因为 ERPNext 要处理单据编号、权限、必填校验、Link 校验、默认值、子表关系和后续生命周期。

## 成功后的 ToolResult

期望返回结构：

```json
{
  "success": true,
  "tool_call_id": "call_...",
  "data": {
    "doctype": "Material Request",
    "name": "MAT-MR-2026-00004",
    "docstatus": 0,
    "submit_tool": "erpnext.buying.submit_document"
  },
  "summary": "Created Material Request draft with 1 item rows.",
  "user_message": "已创建材料申请草稿 MAT-MR-2026-00004，包含帆布手套 100 双，需求日期 2026-06-24，目标仓库为 SCEN-CIVIL 项目仓。"
}
```

## 写入结构化记忆

成功后 Runtime 应记录：

```json
{
  "active_entities": {
    "last_material_request": "MAT-MR-2026-00004",
    "current_project": "PROJ-0001",
    "current_warehouse": "SCEN-CIVIL 项目仓 - SD"
  },
  "last_tool_calls": [
    {
      "tool": "erpnext.buying.create_material_request_draft",
      "result_name": "MAT-MR-2026-00004"
    }
  ]
}
```

这样用户下一句说：

```text
把刚才那张申请提交给项目经理确认。
```

Runtime 才知道“刚才那张申请”是 `MAT-MR-2026-00004`。

## 示例结论

这个示例展示的不是“模型会填 JSON”，而是：

```text
模型抽意图
  -> Runtime 查已有数据
  -> Contract 决定字段怎么填
  -> Resolver 找真实 ID
  -> Validator 拦坏参数
  -> Gateway 控制权限和确认
  -> ERPNext 创建草稿
```

这就是材料申请场景的最小可用 Agent 流程。
