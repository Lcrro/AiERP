# ToolCall 参数编排层设计

本文定义 Agent Runtime 到 ERPNext ToolCall 之间的参数编排层。它解决的问题不是“模型会不会写 JSON”，而是系统如何稳定地把自然语言业务意图编译成合法、完整、可审计、可恢复的 ToolCall。

关联文档：

- [架构路线图](roadmap.md)
- [项目结构与解耦边界](project-structure.md)
- [DocType 索引与 Agent 上下文](doctype-index.md)
- [当前 ToolCall 清单](../reference/toolcall-current-inventory.md)

## 背景

当前 ERPNext Adapter 已经有一批稳定 ToolCall。以 `08:00 管理层查看今日异常` 为例，系统实际需要组合这些工具：

```text
erpnext.search_documents
erpnext.stock.get_balance
erpnext.accounting.accounts_payable
erpnext.buying.run_purchase_analysis
```

这些工具本身能执行，但参数手填难度差异很大：

| ToolCall | 手填难度 | 主要风险 |
|---|---:|---|
| `erpnext.stock.get_balance` | 低 | 物料编码、仓库名抄错 |
| `erpnext.accounting.accounts_payable` | 中 | 公司名、日期格式、报表过滤器不规范 |
| `erpnext.buying.run_purchase_analysis` | 中 | 报表名、过滤器、日期范围不规范 |
| `erpnext.search_documents` | 高 | Frappe filter DSL 嵌套复杂，字段名/操作符容易错 |

如果让 Agent 直接手写底层 JSON，短期可以演示，长期会在复杂业务里不断翻车。因此参数编排层必须成为 Agent Runtime 的核心基础设施。

## 目标

参数编排层的目标：

- 让 Agent 只表达业务意图和必要槽位，不直接拼底层 Frappe JSON。
- 从用户上下文、岗位上下文、ERPNext 主数据和对话记忆中自动补参数。
- 对公司、仓库、项目、物料、供应商、DocType、字段名、日期等关键值做解析和校验。
- 在执行前完成 schema 校验、字段校验、权限/风险预检和必要的 preview。
- 把缺参数、歧义候选、非法字段、权限失败变成可修复流程，而不是直接报错。
- 保留最终 ToolCall 和 ToolResult 的审计链路。

不在本文范围：

- 大模型框架选型的最终绑定。
- 监管 Agent 的审批策略。
- 全量业务 wrapper 的具体实现。
- ERPNext 权限模型替代。

## 核心原则

第一，Agent 不直接手写底层查询 JSON。  
尤其是 `erpnext.search_documents`、`erpnext.call_method`、裸 `erpnext.create_document` 这类高自由度工具，默认只给编排层使用。

第二，Agent 输出的是意图，不是最终执行参数。  
例如用户说“今天有哪些应付快到期”，Agent 应该产出：

```json
{
  "intent": "check_accounts_payable",
  "time_range": "today",
  "party": null
}
```

而不是直接产出：

```json
{
  "tool": "erpnext.accounting.accounts_payable",
  "arguments": {
    "company": "STEC (Demo)",
    "from_date": "2026-06-01",
    "to_date": "2026-06-16"
  }
}
```

第三，能从上下文确定的参数不让模型猜。  
`company`、当前用户、岗位、默认项目、默认仓库、site、today 等由 Runtime 注入。

第四，所有关键字符串先 resolve 再执行。  
“中心仓”先解析成 `蕰川路基地仓库 - SD`；“帆布手套”先解析成 `SAFE-000005`；“STEC”先解析成 `STEC (Demo)`。

第五，复杂操作走 preview / draft / submit。  
查询可以直接执行；创建草稿可以自动或半自动；提交、财务、权限、库存移动必须显式确认。

第六，员工 Agent 不直接面对全量 ToolCall。  
`ERPNextAdapter` 是底层执行器，可以执行所有已注册工具；员工 Agent 必须经过 `ToolGateway`，由岗位 profile 决定哪些工具可见、可执行。即使模型猜中了隐藏工具名，只要不在当前 profile 允许范围内，也会在进入 Adapter 前被拒绝。

第七，ToolCall 必须绑定员工本人的 ERPNext 身份。  
网页登录采购员并不自动代表后端 ToolCall 也在用采购员身份。生产架构里，Runtime 必须用当前员工的 ERPNext session/API token 创建 Adapter，并可通过 `erpnext.get_logged_user` 做身份核验。如果发现 ToolCall 使用的是管理员或其他账号 token，Gateway 应拒绝执行。

## 总体流程

```text
用户自然语言
  -> Intent Router
  -> Slot Extractor
  -> Runtime Context Injector
  -> Entity Resolver
  -> Tool Planner
  -> Parameter Builder
  -> Validator / Preflight
  -> Tool Gateway
  -> ToolCall Executor / ERPNext Adapter
  -> ToolResult Normalizer
  -> Structured Memory Update
  -> Agent 回复用户
```

### 1. Intent Router

职责：判断用户要做哪类业务。

输出示例：

```json
{
  "intent": "manager_daily_risk_summary",
  "domain": "management",
  "risk": "read_only",
  "requires_business_wrapper": true
}
```

典型路由目标：

| 意图 | 推荐业务入口 |
|---|---|
| 管理层晨检 | `biz.get_manager_daily_risks` |
| 查库存 | `biz.check_stock_balance` 或 `erpnext.stock.get_balance` |
| 查应付 | `biz.get_accounts_payable_summary` |
| 待采购汇总 | `biz.list_pending_purchase_requests` |
| 创建材料申请 | `biz.prepare_material_request` |
| 项目领料 | `biz.prepare_project_material_issue` |

### 2. Slot Extractor

职责：从用户话里提取槽位，但不负责补全和规范化。

输出示例：

```json
{
  "raw_slots": {
    "item_text": "帆布手套",
    "warehouse_text": "中心仓",
    "date_text": "今天"
  }
}
```

### 3. Runtime Context Injector

职责：注入模型不应该猜的上下文。

上下文示例：

```json
{
  "site": "civil",
  "today": "2026-06-16",
  "user": "pan.feng@stec-up.local",
  "employee_name": "赵强",
  "role": "采购主管",
  "company": "STEC (Demo)",
  "default_warehouse": "蕰川路基地仓库 - SD",
  "default_project": null
}
```

### 4. Entity Resolver

职责：把自然语言名词解析成 ERPNext 里的正式值。

| 槽位 | Resolver | 输出 |
|---|---|---|
| 物料 | item resolver | `item_code`、候选、置信度、追问 |
| 仓库 | warehouse resolver | `warehouse` |
| 公司 | company resolver | `company` |
| 项目 | project resolver | `project` |
| 供应商 | supplier resolver | `supplier` |
| 日期 | date resolver | ISO 日期 |
| DocType | doctype resolver | ERPNext 标准 DocType |
| 字段名 | field resolver | DocType meta 中存在的字段 |

Resolver 返回三种状态：

```text
resolved              唯一且可信
needs_confirmation    有候选，但需要确认
needs_clarification   信息不足，必须追问
```

### 5. Tool Planner

职责：决定使用业务工具、模块工具还是底层工具。

工具分层：

| 层级 | 名称 | 暴露给 Agent | 例子 |
|---|---|---:|---|
| L1 | 业务包装工具 | 默认暴露 | `biz.get_manager_daily_risks` |
| L2 | 模块专用工具 | 谨慎暴露 | `erpnext.stock.get_balance` |
| L3 | 通用底层工具 | 默认不直接暴露 | `erpnext.search_documents` |
| L4 | 裸方法/裸文档工具 | 仅系统内部或专家模式 | `erpnext.call_method`、`erpnext.create_document` |

### Tool Gateway 与工具隔离

当前代码新增了 Agent Runtime 边界：

```text
ToolCall
  -> ToolGateway
      -> ToolAccessPolicy
      -> ERPNext 身份核验
  -> ERPNextAdapter
  -> ERPNext/Frappe API
```

三个工具暴露级别：

| 暴露级别 | 含义 | 例子 |
|---|---|---|
| `agent_visible` | 可按岗位 profile 暴露给员工 Agent | `erpnext.buying.create_material_request_draft`、`erpnext.stock.get_balance` |
| `runtime_internal` | 只给编排层/Resolver 使用，模型直接调用会被拒绝 | `erpnext.search_documents`、`erpnext.get_document`、`erpnext.run_report` |
| `developer_only` | 只给开发/初始化/专家模式，普通员工 profile 永不暴露 | `erpnext.create_document`、`erpnext.update_document`、`erpnext.call_method`、`erpnext.setup_item_master` |

岗位 profile 第一版：

| Profile | 典型可见工具 |
|---|---|
| 采购员 / 采购主管 | 采购专用工具、库存只读工具、物料搜索、评论和 ToDo |
| 仓库员 / 仓库主管 | 库存专用工具、物料搜索、评论和 ToDo |
| 财务 / 财务主管 | 财务专用工具、物料搜索、评论和 ToDo |
| 项目经理 / 班组长 | 项目专项工具、库存只读工具、材料申请草稿 |
| 管理层 | 报表、异常、库存和采购只读/预览类工具 |
| 系统管理员 | 用户与权限专项工具 |
| developer | 全量工具，仅开发和本地调试使用 |

这层不替代 ERPNext 权限。它解决的是“模型能不能请求这个工具”；ERPNext 后端权限解决的是“当前员工账号有没有权操作这个 DocType/单据”。两层必须同时存在：

```text
工具门禁：防止 Agent 拿到不该拿的工具。
ERPNext 权限：防止员工账号执行不该执行的业务动作。
```

因此，采购员如果试图构造库存盘点或裸 `create_document` ToolCall，会先被 Gateway 拒绝；如果调用的是采购员 profile 允许的采购收货 ToolCall，ERPNext 仍会按采购员账号的后端权限、工作流和单据校验做最终裁决。

### 6. Parameter Builder

职责：把 resolved slots 和上下文编译成 ToolCall 参数。

例如库存查询：

```json
{
  "tool": "erpnext.stock.get_balance",
  "arguments": {
    "item_code": "SAFE-000005",
    "warehouse": "蕰川路基地仓库 - SD",
    "limit": 100
  }
}
```

例如 ToDo 查询，Agent 不直接写 Frappe DSL，Builder 负责生成：

```json
{
  "tool": "erpnext.search_documents",
  "arguments": {
    "doctype": "ToDo",
    "filters": {
      "status": "Open",
      "description": ["like", "%AGENT-PREP%"]
    },
    "fields": ["name", "allocated_to", "priority", "description", "reference_type", "reference_name"],
    "limit": 20,
    "order_by": "modified desc"
  }
}
```

### 7. Validator / Preflight

职责：执行前拦截坏参数。

校验类型：

| 校验 | 例子 |
|---|---|
| JSON schema | 必填字段、字段类型、枚举 |
| 上下文必填 | 当前用户必须有 company |
| 实体存在 | item_code、warehouse、supplier 是否存在 |
| DocType 字段 | `fields` 和 `filters` 是否在 DocType meta 中存在 |
| 日期格式 | 必须是 `YYYY-MM-DD` |
| 风险等级 | L4/L5 必须带 confirmation |
| 业务前置条件 | MR 必须提交后才能转 PO |

校验失败时，不直接执行，返回 repair instruction：

```json
{
  "status": "needs_repair",
  "error_type": "invalid_field",
  "message": "Stock Entry 不允许查询字段 title。",
  "repair": {
    "remove_fields": ["title"],
    "retry_allowed": true
  }
}
```

### 8. ToolResult Normalizer

职责：把工具返回变成 Agent 易读、可记忆的结构。

例如：

```json
{
  "summary": "中心仓帆布手套现货 300 双。",
  "entities": [
    {
      "type": "Item",
      "id": "SAFE-000005",
      "label": "帆布手套"
    },
    {
      "type": "Warehouse",
      "id": "蕰川路基地仓库 - SD"
    }
  ],
  "facts": [
    {
      "key": "actual_qty",
      "value": 300,
      "unit": "双"
    }
  ],
  "next_actions": ["review_project_need", "create_material_request_if_needed"]
}
```

### 9. Structured Memory Update

职责：把重要业务 ID 和状态写入结构化记忆。

记忆对象示例：

```json
{
  "active_entities": {
    "last_material_request": "MAT-MR-2026-00002",
    "last_purchase_order": "PUR-ORD-2026-00001",
    "last_purchase_receipt": "MAT-PRE-2026-00001",
    "last_purchase_invoice": "ACC-PINV-2026-00001"
  },
  "scenario_state": {
    "current_step": "16:00",
    "completed_steps": ["08:00", "08:20", "09:10", "10:00", "13:30", "16:00"]
  }
}
```

这一步很关键。沙盘里已经暴露过一个真实问题：如果 Runtime 没有可靠记住新生成单号，后续提交或验证时很容易拿错旧单号。

## 四个工具的编排策略

### `erpnext.stock.get_balance`

暴露策略：可以给 Agent 直接用，但参数仍应 resolver 化。

输入来源：

| 参数 | 来源 |
|---|---|
| `item_code` | item resolver |
| `warehouse` | warehouse resolver 或用户默认仓库 |
| `limit` | 系统默认 |

推荐编排：

```text
用户：中心仓还有多少帆布手套？
  -> item_text=帆布手套
  -> warehouse_text=中心仓
  -> resolve item SAFE-000005
  -> resolve warehouse 蕰川路基地仓库 - SD
  -> erpnext.stock.get_balance
```

### `erpnext.accounting.accounts_payable`

暴露策略：建议通过业务 wrapper 使用。

输入来源：

| 参数 | 来源 |
|---|---|
| `company` | Runtime context |
| `from_date` | 日期策略 |
| `to_date` | Runtime today |
| `party` | supplier/customer resolver，可选 |
| `filters` | Builder 生成 |

推荐业务入口：

```text
biz.get_accounts_payable_summary
```

内部再编译为：

```json
{
  "tool": "erpnext.accounting.accounts_payable",
  "arguments": {
    "company": "STEC (Demo)",
    "from_date": "2026-06-01",
    "to_date": "2026-06-16"
  }
}
```

### `erpnext.buying.run_purchase_analysis`

暴露策略：建议通过业务 wrapper 使用。

输入来源：

| 参数 | 来源 |
|---|---|
| `report_name` | 固定白名单，默认 `Purchase Analytics` |
| `filters.company` | Runtime context |
| `filters.from_date` | 日期策略 |
| `filters.to_date` | Runtime today |

推荐业务入口：

```text
biz.get_purchase_overview
biz.get_supplier_purchase_summary
```

### `erpnext.search_documents`

暴露策略：默认不直接给自然语言 Agent。只给参数编排层、业务 wrapper 或专家调试模式用。

输入来源：

| 参数 | 来源 |
|---|---|
| `doctype` | 业务工具固定或 doctype resolver |
| `filters` | Query Builder 生成 |
| `fields` | DocType profile 白名单 |
| `limit` | 工具默认或业务工具固定 |
| `order_by` | 业务工具固定或受控枚举 |

推荐业务入口示例：

```text
biz.get_manager_open_risks
biz.list_pending_material_requests
biz.list_overdue_purchase_orders
biz.get_document_comments
```

Query Builder 输入示例：

```json
{
  "doctype": "ToDo",
  "where": [
    {"field": "status", "op": "eq", "value": "Open"},
    {"field": "description", "op": "contains", "value": "AGENT-PREP"}
  ],
  "view": "manager_risk_list"
}
```

Builder 输出 Frappe 参数：

```json
{
  "doctype": "ToDo",
  "filters": {
    "status": "Open",
    "description": ["like", "%AGENT-PREP%"]
  },
  "fields": ["name", "allocated_to", "priority", "description", "status"],
  "limit": 20,
  "order_by": "modified desc"
}
```

## 业务 Wrapper 设计

参数编排层应该优先推动新增业务 wrapper，而不是让 Agent 频繁碰底层通用工具。

第一批建议 wrapper：

| 业务工具 | 内部可能调用 |
|---|---|
| `biz.get_manager_daily_risks` | ToDo、Bin、AP、PO、MR、Purchase Analysis |
| `biz.check_stock_balance` | item resolver、warehouse resolver、`stock.get_balance` |
| `biz.get_accounts_payable_summary` | `accounting.accounts_payable` |
| `biz.list_pending_purchase_requests` | MR、Item Price、Supplier |
| `biz.list_overdue_purchase_orders` | PO、ToDo、Comment |
| `biz.prepare_material_request` | item resolver、stock preview、MR draft |
| `biz.prepare_project_material_issue` | stock preview、project resolver、Stock Entry draft |

业务 wrapper 的输出必须稳定：

```json
{
  "status": "ready",
  "summary": "...",
  "tool_calls": [],
  "entities": [],
  "missing_slots": [],
  "questions": [],
  "next_actions": []
}
```

## Tool Profile

每个工具需要有一份 Runtime 可读的 profile。它不是当前 JSON schema 的替代，而是给编排层看的操作说明。

示例：

```yaml
tool: erpnext.search_documents
exposure: internal_only
risk: L0
requires:
  - doctype
builders:
  - frappe_filter_builder
validators:
  - json_schema
  - doctype_exists
  - fields_exist
  - filters_valid
defaults:
  limit: 20
repair:
  invalid_field: remove_or_replace_field
  bad_filter_operator: map_operator
```

建议位置：

```text
src/nexterp_agent/agent_runtime/tool_profiles/
```

## Repair Loop

参数编排层允许有限自动修复，但不能无限重试。

流程：

```text
build ToolCall
  -> validate
  -> if ok execute
  -> if repairable repair once or twice
  -> if ambiguous ask user
  -> if high risk request confirmation
  -> if unsafe stop
```

可自动修复：

- 日期格式归一
- 公司简称解析
- 仓库简称解析
- `contains` 转成 Frappe `["like", "%...%"]`
- 移除不允许查询的显示字段
- 补默认 `limit`

必须追问：

- 多个物料候选置信度接近
- 规格不足且会影响 SKU
- 没有默认项目/仓库
- 财务动作金额或对象不明确
- 高风险提交缺确认

必须停止：

- 权限不足
- 工具不支持该动作
- DocType 或字段不存在且无法修复
- 用户要求绕过确认或审计

## 状态与记忆

Runtime 不能只依赖聊天上下文。需要结构化状态。

建议最小状态：

```json
{
  "conversation_id": "...",
  "user_context": {},
  "active_entities": {},
  "last_tool_calls": [],
  "last_tool_results": [],
  "pending_confirmations": [],
  "scenario_state": {}
}
```

需要长期保留的业务对象：

- 最近创建的 MR、PO、PR、PI、Stock Entry
- 当前项目、仓库、供应商
- 用户刚确认过的物料候选
- 待追问槽位
- 待提交草稿

## 风险控制

参数编排层不替代后续监管 Agent，但要先做基础风险门。

| 风险 | 行为 |
|---|---|
| L0 只读 | 可自动执行 |
| L1 预览 | 可自动执行，但结果需解释 |
| L3 草稿 | 可创建草稿，需记录来源意图 |
| L4 提交/库存影响 | 必须 confirmation |
| L5 财务/权限 | 必须强 confirmation，后续接监管 |

confirmation 最小字段：

```json
{
  "confirmed_by": "user@example.com",
  "confirmed_at": "2026-06-16T10:30:00",
  "confirmation_text": "确认提交采购订单。",
  "reason": "供应商、数量、价格和交期已核对。"
}
```

## 和 LangGraph / MCP 的关系

参数编排层应该独立于具体 Agent 框架。

建议：

- LangGraph 可用于多步状态流转，例如采购申请到采购订单到收货到发票。
- MCP Server 可用于把稳定工具暴露给不同 Agent 客户端。
- 参数编排层本身应作为可复用核心模块，既能被 LangGraph 节点调用，也能被 MCP tool handler 调用。

推荐边界：

```text
LLM / Agent Framework
  -> Intent / ActionPlan
  -> Parameter Orchestration Core
  -> ToolCall
  -> ERPNext Adapter
```

这样未来换 Agent 框架，不会重写 ERPNext 参数规则。

## 建议代码结构

建议新增：

```text
src/nexterp_agent/agent_runtime/
  __init__.py
  context.py
  intents.py
  memory.py
  router.py
  slots.py
  resolvers.py
  builders.py
  validators.py
  repair.py
  planner.py
  orchestrator.py
  tool_profiles/
    generic.yaml
    stock.yaml
    buying.yaml
    accounting.yaml
```

参数编排通过 DeepSeek Runtime 和结构化模拟模型序列共同验证。

## v0.1 开发顺序

1. 建 `ToolProfile` 数据结构和 profile 文件。
2. 建 `RuntimeContext`，自动注入 `company`、`today`、`user`、默认仓库。
3. 建 resolver：
   - `resolve_company`
   - `resolve_warehouse`
   - `resolve_item`
   - `resolve_supplier`
4. 建 `FrappeFilterBuilder`，把受控查询意图转成 `search_documents` 参数。
5. 建 validator：
   - JSON schema 校验
   - 日期校验
   - entity existence 校验
   - DocType field 校验
6. 先实现 4 个编排用例：
   - 查库存
   - 查应付
   - 查管理层 open risks
   - 查采购分析
7. 接入自然语言 Agent Runtime。
8. 用结构化模拟序列和本地 ERPNext 集成测试验收。

## 验收用例

### 用例 1：查库存

输入：

```text
中心仓还有多少帆布手套？
```

期望：

- 解析 `帆布手套 -> SAFE-000005`
- 解析 `中心仓 -> 蕰川路基地仓库 - SD`
- 生成 `erpnext.stock.get_balance`
- 返回现货数量和估值

### 用例 2：查应付

输入：

```text
今天有哪些应付快到期？
```

期望：

- 自动注入 `company`
- 自动生成日期范围
- 调用 `erpnext.accounting.accounts_payable`
- 返回按供应商分组的应付摘要

### 用例 3：查管理层风险

输入：

```text
今天公司有哪些异常需要我关注？
```

期望：

- 不让 Agent 直接写 `search_documents` filters
- 由 `biz.get_manager_daily_risks` 或 Builder 生成 ToDo、Bin、AP、PO、MR 查询
- 输出风险列表、优先级和下一步动作

### 用例 4：非法字段修复

输入：

```json
{
  "doctype": "Stock Entry",
  "fields": ["name", "title"]
}
```

期望：

- validator 发现 `title` 不是允许查询字段
- 自动移除或替换为安全字段
- 记录 repair
- 不把误分类的 `auth_error` 暴露给用户

## 当前结论

ToolCall 参数编排层是 Agent Runtime 的“编译器”。它把业务意图、用户上下文、主数据解析、DocType schema 和风险策略合成一个合法 ToolCall。

后续真正要让 Agent 稳定工作，重点不是让模型背 150 个工具的 JSON 格式，而是让它学会：

```text
识别业务意图
提取少量槽位
知道何时追问
把执行交给参数编排层
```

这会把系统从“模型手写 API 参数”升级为“业务意图编译成可控 ERP 操作”。
