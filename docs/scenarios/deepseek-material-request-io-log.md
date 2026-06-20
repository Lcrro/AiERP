# DeepSeek 材料申请试验：输入输出记录

本文记录本轮 DeepSeek 材料申请 ToolCall 试验的可读输入、模型输出、发现的问题和后续修正。

不记录 `.env`、API key、HTTP Authorization header 或任何真实密钥。

## 试验目标

验证：

```text
员工自然语言
  -> DeepSeek 生成候选 ToolCall
  -> Runtime 校验/修正上下文
  -> ToolGateway 执行
  -> ERPNext UI 可见材料申请草稿
```

本轮只允许 DeepSeek 生成这个工具：

```text
erpnext.buying.create_material_request_draft
```

## 共同系统输入

### API 请求形态

```json
{
  "base_url": "https://api.deepseek.com",
  "endpoint": "/chat/completions",
  "model": "deepseek-v4-flash",
  "response_format": {"type": "json_object"},
  "temperature": 0.1,
  "stream": false
}
```

### 核心系统提示词

第一次和第二次调用时的核心提示词：

```text
你是 ERPNext 材料申请 ToolCall 编排器，只负责把用户自然语言整理成候选 ToolCall。
你不能执行工具，不能假装已经创建单据，不能编造 ERPNext 主键。
如果物料、仓库、项目、日期或数量缺失或不确定，返回 needs_clarification 并提出最少必要问题。
如果信息足够，返回 needs_confirmation，并生成 erpnext.buying.create_material_request_draft 的候选参数。
数量必须是数字；日期必须是 YYYY-MM-DD；items 必须是数组。
item_code、warehouse、project 只能使用上下文中已经解析出的标准值；没有标准值时不要凭空造。
只输出一个 JSON object，不要 Markdown，不要解释性正文。
```

第三次调用前新增了一条规则：

```text
如果 runtime_context.default_schedule_date 已提供，必须用它作为需求日期，不要再追问今天日期。
```

### 输出 Schema

```json
{
  "status": "needs_clarification | needs_confirmation",
  "questions": ["string"],
  "tool_call": {
    "tool": "erpnext.buying.create_material_request_draft",
    "arguments": {
      "material_request_type": "Purchase",
      "company": "ERPNext company name",
      "schedule_date": "YYYY-MM-DD",
      "items": [
        {
          "item_code": "resolved Item.name",
          "qty": 1,
          "uom": "resolved UOM",
          "warehouse": "resolved Warehouse.name",
          "schedule_date": "YYYY-MM-DD",
          "project": "resolved Project.name"
        }
      ]
    }
  },
  "candidate_summary": "string",
  "assumptions": ["string"],
  "confidence": 0.0
}
```

## 调用 1：初始 dry-run

### 用户输入

```text
城东项目道路班组明天需要帆布手套100双，送到城东项目仓，用于劳保补充。
```

### Runtime 上下文输入

当时的上下文是演示值，项目和仓库名称还没有完全对齐真实 civil 站点：

```json
{
  "company": "STEC (Demo)",
  "default_schedule_date": "2026-06-18",
  "project_candidates": [
    {
      "name": "SCEN-CIVIL-CHENGDONG",
      "label": "城东项目"
    }
  ],
  "warehouse_candidates": [
    {
      "name": "SCEN-CIVIL 城东项目仓 - SD",
      "label": "城东项目仓"
    }
  ],
  "item_candidates": [
    {
      "item_code": "SAFE-000005",
      "item_name": "帆布手套",
      "stock_uom": "双",
      "aliases": ["帆布手套", "劳保手套"]
    }
  ]
}
```

### DeepSeek 输出

```json
{
  "status": "needs_confirmation",
  "questions": [],
  "tool_call": {
    "tool": "erpnext.buying.create_material_request_draft",
    "arguments": {
      "material_request_type": "Purchase",
      "company": "STEC (Demo)",
      "schedule_date": "2026-06-19",
      "items": [
        {
          "item_code": "SAFE-000005",
          "qty": 100,
          "uom": "双",
          "warehouse": "SCEN-CIVIL 城东项目仓 - SD",
          "schedule_date": "2026-06-19",
          "project": "SCEN-CIVIL-CHENGDONG"
        }
      ]
    }
  },
  "candidate_summary": "为城东项目申请100双帆布手套，送至城东项目仓，需求日期2026-06-19，用于劳保补充。",
  "assumptions": [
    "默认材料申请类型为Purchase",
    "默认公司为STEC (Demo)",
    "默认需求日期为明天（2026-06-19）"
  ],
  "confidence": 0.95
}
```

### 发现的问题

- 日期错了：当前日期是 `2026-06-17`，用户说“明天”应为 `2026-06-18`，模型输出 `2026-06-19`。
- 项目和仓库来自演示上下文，不是真实 civil 站点的标准主键。

### 结论

相对日期、项目、仓库、物料主键不能完全交给模型。Runtime 必须把 resolver 结果作为最终权威值。

## ERPNext 写入：人工修正后执行

这一步不是 DeepSeek 输出，而是我们根据调用 1 暴露的问题，人工按 Runtime 应有规则修正后，通过 `ToolGateway` 执行。

### 执行 ToolCall

```json
{
  "tool": "erpnext.buying.create_material_request_draft",
  "arguments": {
    "material_request_type": "Purchase",
    "company": "STEC (Demo)",
    "schedule_date": "2026-06-18",
    "items": [
      {
        "item_code": "SAFE-000005",
        "qty": 100,
        "uom": "双",
        "warehouse": "SCEN-CIVIL 项目仓 - SD",
        "schedule_date": "2026-06-18",
        "project": "PROJ-0001"
      }
    ]
  }
}
```

### ERPNext 返回

```json
{
  "ok": true,
  "data": {
    "doctype": "Material Request",
    "name": "MAT-MR-2026-00003",
    "docstatus": 0,
    "status": "Draft",
    "summary": "Created Material Request draft with 1 item rows.",
    "next_actions": ["review_draft", "confirm_submit"],
    "risk": {
      "level": "L3",
      "requires_confirmation_for_submit": true,
      "submit_tool": "erpnext.buying.submit_document"
    }
  }
}
```

### UI 验证

ERPNext 页面已看到：

```text
材料申请：MAT-MR-2026-00003
标题：采购申请帆布手套
状态：草案
目的：采购
交易日期：2026-06-17
必需日期：2026-06-18
物料：SAFE-000005 帆布手套
数量：100
```

## Runtime 修正

随后加入 `normalize_material_request_plan`，规则是：

```text
DeepSeek 负责理解意图；
Runtime 负责确定性主数据和日期；
如果上下文里只有一个解析候选，就覆盖模型输出；
覆盖动作记录到 runtime_corrections。
```

会覆盖的字段：

```text
company
schedule_date
items[].item_code
items[].uom
items[].warehouse
items[].project
items[].schedule_date
```

同时加强校验：

```text
company 必填
schedule_date 必填
items 非空
items[].item_code 必填
items[].qty 必须为正数
items[].warehouse 必填
items[].schedule_date 必填
```

## 调用 2：真实上下文但提示词还不够明确

### 用户输入

```text
城东项目道路班组明天需要帆布手套100双，送到项目仓，用于劳保补充。
```

### Runtime 上下文输入

这时已经把项目和仓库修正成真实 civil 站点数据，但还没有加入 `current_date`，提示词也还没有明确“必须使用 default_schedule_date”。

```json
{
  "company": "STEC (Demo)",
  "default_schedule_date": "2026-06-18",
  "project_candidates": [
    {
      "name": "PROJ-0001",
      "label": "城东道路改造项目"
    }
  ],
  "warehouse_candidates": [
    {
      "name": "SCEN-CIVIL 项目仓 - SD",
      "label": "项目仓"
    }
  ],
  "item_candidates": [
    {
      "item_code": "SAFE-000005",
      "item_name": "帆布手套",
      "stock_uom": "双",
      "aliases": ["帆布手套", "劳保手套"]
    }
  ]
}
```

### DeepSeek 输出

```json
{
  "status": "needs_clarification",
  "questions": [
    "请提供今天的日期，以便将'明天'转换为具体日期。"
  ],
  "tool_call": null,
  "candidate_summary": "",
  "assumptions": [],
  "confidence": 0.0
}
```

### 发现的问题

模型变谨慎了，但没有主动使用 `runtime_context.default_schedule_date`。

### 结论

提示词需要明确告诉模型：如果 Runtime 已经提供确定日期，就不要再问今天是哪天。

## 调用 3：加入日期规则后的 dry-run

### 用户输入

```text
城东项目道路班组明天需要帆布手套100双，送到项目仓，用于劳保补充。
```

### Runtime 上下文输入

```json
{
  "company": "STEC (Demo)",
  "current_date": "2026-06-17",
  "default_schedule_date": "2026-06-18",
  "project_candidates": [
    {
      "name": "PROJ-0001",
      "label": "城东道路改造项目"
    }
  ],
  "warehouse_candidates": [
    {
      "name": "SCEN-CIVIL 项目仓 - SD",
      "label": "项目仓"
    }
  ],
  "item_candidates": [
    {
      "item_code": "SAFE-000005",
      "item_name": "帆布手套",
      "stock_uom": "双",
      "aliases": ["帆布手套", "劳保手套"]
    }
  ]
}
```

### DeepSeek 输出

```json
{
  "status": "needs_confirmation",
  "questions": [],
  "tool_call": {
    "tool": "erpnext.buying.create_material_request_draft",
    "arguments": {
      "material_request_type": "Purchase",
      "company": "STEC (Demo)",
      "schedule_date": "2026-06-18",
      "items": [
        {
          "item_code": "SAFE-000005",
          "qty": 100,
          "uom": "双",
          "warehouse": "SCEN-CIVIL 项目仓 - SD",
          "schedule_date": "2026-06-18",
          "project": "PROJ-0001"
        }
      ]
    }
  },
  "candidate_summary": "为城东道路改造项目采购100双帆布手套，需求日期2026-06-18，存放至项目仓，用于劳保补充。",
  "assumptions": [
    "帆布手套对应物料编码SAFE-000005，单位为双。",
    "项目仓为SCEN-CIVIL 项目仓 - SD。",
    "项目为城东道路改造项目（PROJ-0001）。",
    "需求日期为明天2026-06-18（从上下文获取）。",
    "材料申请类型默认为采购。"
  ],
  "confidence": 0.95,
  "runtime_corrections": []
}
```

### 结果

这次模型正确使用了 Runtime 上下文：

```text
日期：2026-06-18
项目：PROJ-0001
仓库：SCEN-CIVIL 项目仓 - SD
物料：SAFE-000005
数量：100 双
```

因为模型输出已经与 Runtime 上下文一致，所以：

```json
"runtime_corrections": []
```

## 最终结论

这轮试验证明了一个重要架构结论：

```text
LLM 适合做人话理解和候选 ToolCall 生成；
Runtime 必须负责日期、主数据、权限、字段约束和最终执行边界。
```

更具体地说：

- DeepSeek 可以把“帮我申请帆布手套”翻译成 Material Request ToolCall。
- 但日期、项目、仓库、物料编码不能让模型自由猜。
- Runtime 应先 resolver 出候选，再把候选作为上下文给模型。
- Runtime 最后还要覆盖/校验模型输出。
- 只有通过 `ToolGateway` 的 ToolCall 才能进入 ERPNext Adapter。

