# Agent 使用 ToolCall 的统一方案

本文把前期关于 Agent、ToolCall、表单编排、Resolver、权限和记忆的讨论整理成一套统一方案。

核心结论：

```text
不要让大模型直接填写 ERPNext ToolCall。
要让大模型表达业务意图，由 Runtime 根据 ToolCall 契约、主数据和用户上下文编译成合法 ToolCall。
```

这套方案的目标不是让模型“背会 150 个工具”，而是让系统稳定地把员工的人话变成可执行、可审计、可修复的 ERPNext 操作。

关联文档：

- [ToolCall 参数编排层设计](toolcall-parameter-orchestration.md)
- [项目结构与解耦边界](project-structure.md)
- [ToolCall Data Dictionary](../reference/toolcall-data-dictionary.md)

## 设计判断

### 保留的核心思路

第一，ToolCall 应该像数据库表一样有严格契约。  
每个字段要说明类型、必填、枚举、默认值、外键、格式、最小值、最大值、确认策略和错误修复策略。

第二，ToolCall 还需要一份“填表说明书”。  
JSON Schema 只能说明字段长什么样，不能说明字段从哪里来。因此每个 ToolCall 还要有 `parameter_plan`，说明字段来源、Resolver、追问策略和确认策略。

第三，Agent Runtime 要有表单编排层。  
表单编排层读取 ToolCall Contract，把自然语言意图、当前用户、ERPNext 主数据、物料库和对话记忆组合成最终 ToolCall。

第四，主数据 ID 不能让模型猜。  
`item_code`、`warehouse`、`project`、`supplier`、`company`、`doctype`、`fieldname` 都必须通过 Resolver 查到真实值。

第五，权限要分两层。  
`ToolGateway` 先限制当前岗位 Agent 能调用哪些工具；ERPNext 后端再用当前员工账号做最终业务权限裁决。

第六，复杂流程要有结构化记忆。  
采购申请、采购订单、收货单、发票、项目、仓库、供应商等业务 ID 不能只藏在聊天记录里，必须写入结构化状态。

### 不采用的做法

不让模型直接面对 150 个 Tool schema。  
工具太多、参数太细，模型容易选错工具或漏字段。

不让模型直接写底层 Frappe 查询。  
例如 `erpnext.search_documents` 的 filters DSL 应由 Query Builder 生成，而不是模型手写。

不把 ERPNext 权限当成唯一防线。  
ERPNext 权限负责最终业务裁决，但 Agent 侧仍要限制工具可见性、确认策略和高风险操作。

不把 RAG 当成唯一方案。  
可以检索 ToolCall 文档和物料文档，但真正执行前必须经过 Contract、Resolver、Validator 和 Gateway。

不把 LangGraph 或 MCP 绑定成核心架构。  
LangGraph 可以做多步流程编排，MCP 可以做工具暴露协议，但参数编排核心应独立存在，方便以后替换 Agent 框架。

## 总体架构

```text
用户自然语言
  -> Intent Router
  -> Slot Extractor
  -> Runtime Context Injector
  -> ToolCall Contract Loader
  -> Resolver Registry
  -> Parameter Orchestrator
  -> Validator / Preflight
  -> Clarifier / Confirmation
  -> ToolGateway
  -> ERPNext Adapter
  -> ERPNext / Frappe API
  -> ToolResult Normalizer
  -> Structured Memory
  -> Agent 回复用户
```

每一层职责必须清楚：

| 层 | 负责什么 | 不负责什么 |
|---|---|---|
| LLM | 理解用户意图，抽取人话槽位，生成解释 | 不编 ERPNext 主键，不绕过规则 |
| Intent Router | 判断属于采购、库存、财务、项目、权限等模块 | 不拼 ToolCall 参数 |
| Slot Extractor | 抽取 `raw_item_text`、数量、日期、人话项目名等 | 不做最终标准化 |
| Runtime Context | 注入当前用户、岗位、公司、今天日期、默认仓库 | 不让模型猜这些值 |
| Resolver | 把人话解析成 ERPNext 真实 ID | 不执行写入 |
| Parameter Orchestrator | 按 ToolCall Contract 填字段、补默认值、组织 ToolCall | 不直接绕过 Gateway |
| Validator | 校验 schema、日期、实体存在性、枚举和业务前置条件 | 不替代 ERPNext 后端校验 |
| Clarifier | 缺字段或多候选时生成追问 | 不强行替用户选择 |
| ToolGateway | 做工具门禁、确认策略、身份核验 | 不替代 ERPNext 权限 |
| ERPNext Adapter | 执行已批准的 ToolCall | 不决定业务意图 |
| Memory | 记录关键业务对象和状态 | 不保存密钥 |

## ToolCall Contract

每个 ToolCall 至少由四部分组成：

```text
schema
  字段类型、必填、枚举、范围、格式

access
  暴露级别、允许岗位、风险等级、确认策略

parameter_plan
  每个字段从哪里来、怎么查、缺了怎么问

backend_mapping
  对应 ERPNext DocType、Report、Frappe Method 或 agent_bridge 方法
```

推荐结构：

```yaml
tool: erpnext.buying.create_material_request_draft
purpose: 创建材料申请草稿
expose: agent_visible
risk: L3
allowed_roles:
  - 采购
  - 项目经理
  - 班组长
confirm: user_confirm

fields:
  company:
    required: true
    type: string
    source: user_context
    resolver: CompanyResolver
    rule: 使用当前登录员工所属公司
    ask_user_if_missing: false

  material_request_type:
    required: true
    type: string
    enum: [Purchase, Material Transfer, Material Issue, Manufacture, Customer Provided]
    source: default
    default: Purchase
    rule: 普通外采需求默认 Purchase

  schedule_date:
    required: true
    type: string
    format: date
    source: natural_language_time
    resolver: DateResolver
    rule: 把“明天、下周一、月底前”解析成 YYYY-MM-DD
    ask_user_if_missing: true
    clarification: 你希望什么时候需要这些物料？

  items[].item_code:
    required: true
    type: string
    source: natural_language_entity
    resolver: ItemResolver
    rule: 禁止模型编物料编码，必须从物料库或 ERPNext Item 查询得到
    ask_user_if_missing: true
    clarification: 你要申请什么物料？
    ambiguity_policy: 多个高相似候选时让用户选择

  items[].qty:
    required: true
    type: number
    minimum: 0.000001
    source: natural_language_number
    rule: 必须是正数
    ask_user_if_missing: true
    clarification: 每种物料需要多少？

  items[].uom:
    required: false
    type: string
    source: item_master_or_user_text
    resolver: UOMResolver
    rule: 优先使用物料主数据默认单位；用户提供单位时校验是否兼容

  items[].warehouse:
    required: true
    type: string
    source: natural_language_or_profile
    resolver: WarehouseResolver
    rule: 把“中心仓、项目仓、西站仓”解析成 ERPNext 仓库全称
    ask_user_if_missing: true
    clarification: 这些物料要送到哪个仓库？

  items[].project:
    required: false
    type: string
    source: natural_language_or_profile
    resolver: ProjectResolver
    rule: 用户提到项目时必须解析成真实 Project 编号
```

## Resolver

Resolver 是这套架构的关键。它负责从已有数据里找出 ToolCall 所需的真实值。

第一版至少需要：

| Resolver | 输入 | 输出 |
|---|---|---|
| `ItemResolver` | 帆布手套、门锁、角铁、水泥 | `item_code`、名称、单位、候选、置信度 |
| `WarehouseResolver` | 中心仓、项目仓、西站仓 | ERPNext 仓库全称 |
| `ProjectResolver` | 合流1.3标、竹白1.2标 | ERPNext Project 编号 |
| `SupplierResolver` | 供应商简称、联系人、历史采购对象 | Supplier 编号 |
| `CompanyResolver` | 当前用户上下文、公司简称 | Company 全称 |
| `DateResolver` | 今天、明天、下周一、月底前 | ISO 日期 |
| `DocTypeResolver` | 中文业务名、模块名 | ERPNext DocType |
| `FieldResolver` | 中文字段名、显示字段 | DocType 字段名 |

Resolver 返回统一结构：

```json
{
  "status": "resolved",
  "value": "SAFE-000005",
  "label": "帆布手套",
  "confidence": 0.96,
  "candidates": [],
  "reason": "别名和标准名称精确匹配，单位为双"
}
```

如果不唯一：

```json
{
  "status": "needs_confirmation",
  "value": null,
  "candidates": [
    {"value": "METAL-000007", "label": "角铁 50*50*6", "confidence": 0.86},
    {"value": "METAL-000043", "label": "角钢 40*40*5", "confidence": 0.83}
  ],
  "question": "你要的是 50*50*6 的角铁，还是 40*40*5 的角钢？"
}
```

如果信息不足：

```json
{
  "status": "needs_clarification",
  "missing": ["规格"],
  "question": "角铁需要什么规格？例如 50*50*6 或 40*40*5。"
}
```

## Material Resolver 推荐方案

物料是最容易出错的 Resolver，不能只靠向量检索。

推荐采用多路召回加重排：

```text
用户原文
  -> 文本归一化
  -> 编码精确匹配
  -> 标准名称/别名匹配
  -> 关键词和规格匹配
  -> pg_trgm 模糊匹配
  -> 全文检索
  -> 向量语义检索
  -> 单位、规格、分组、历史采购权重重排
  -> 置信度策略
```

置信度策略：

| 情况 | 行为 |
|---|---|
| 唯一高置信候选 | 可填入 ToolCall，但高风险写入前仍展示确认 |
| 多个候选接近 | 追问用户选择 |
| 找到名称但规格缺失 | 追问关键规格 |
| 没有候选 | 进入新增物料流程 |
| 用户说的是类别而非 SKU | 展示候选，不强行选唯一物料 |

## 参数编排流程

以材料申请为例：

用户说：

```text
明天合流1.3标要 100 双帆布手套，送项目仓。
```

LLM 只输出意图草稿：

```json
{
  "intent": "create_material_request",
  "project_text": "合流1.3标",
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

Runtime 做确定性处理：

```text
DateResolver: 明天 -> 2026-06-23
ProjectResolver: 合流1.3标 -> PROJ-0010
WarehouseResolver: 项目仓 -> 合流1.3标仓库 - SD
ItemResolver: 帆布手套 -> SAFE-000005
UOMResolver: 双 -> 双，且与物料主单位兼容
CompanyResolver: 当前员工 -> STEC (Demo)
```

最终生成 ToolCall：

```json
{
  "tool": "erpnext.buying.create_material_request_draft",
  "arguments": {
    "company": "STEC (Demo)",
    "material_request_type": "Purchase",
    "schedule_date": "2026-06-23",
    "items": [
      {
        "item_code": "SAFE-000005",
        "qty": 100,
        "uom": "双",
        "warehouse": "合流1.3标仓库 - SD",
        "project": "PROJ-0010",
        "schedule_date": "2026-06-23"
      }
    ]
  }
}
```

## 缺字段、多候选和确认

Runtime 不能用猜测掩盖业务不确定性。

| 情况 | 应对 |
|---|---|
| 必填字段缺失 | 追问 |
| 多个候选置信度接近 | 让用户选 |
| 默认值来自岗位配置 | 自动填，并在摘要里说明 |
| 高风险动作 | 执行前确认 |
| 后端报字段错误 | 尝试一次受控修复 |
| 后端报权限不足 | 停止，不自动换管理员账号 |
| 用户要求绕过流程 | 停止并说明需要按权限/审批执行 |

追问要像业务助理，不要像接口报错：

```text
我找到了两种“角铁”：50*50*6 和 40*40*5。你这次要哪一种？
```

而不是：

```text
items[0].item_code 缺失。
```

## 工具分层

150 个 ToolCall 不应该全部直接暴露给员工 Agent。

| 层级 | 类型 | 是否直接给员工 Agent | 说明 |
|---|---|---:|---|
| L1 | 业务包装工具 | 是 | 面向业务动作，例如创建材料申请、待采购汇总 |
| L2 | 模块专用工具 | 有选择地给 | 例如查库存、创建采购订单草稿 |
| L3 | 通用文档/查询工具 | 默认不给 | 编排层内部使用 |
| L4 | 裸 method / 裸 DocType 写入 | 不给 | 开发、初始化、专家模式 |

推荐暴露策略：

```text
员工 Agent
  主要看见 L1 + 少量 L2

Runtime / Resolver
  可以使用受控 L3

Developer
  本地调试时可使用 L4
```

## 权限和安全边界

员工登录 ERPNext 页面，不等于后端 ToolCall 自动使用员工身份。生产架构必须做到：

```text
当前员工登录
  -> Runtime 绑定该员工 ERPNext session / API token
  -> ToolGateway 核验 profile 和登录用户
  -> Adapter 使用该员工身份调用 ERPNext
  -> ERPNext 后端权限和工作流最终裁决
```

因此安全边界是：

```text
ToolGateway:
  当前岗位能不能请求这个工具

ERPNext:
  当前员工账号能不能操作这个单据和 DocType

Confirmation:
  高风险动作是否得到用户明确确认

Audit:
  谁在什么时候基于什么用户意图调用了什么 ToolCall
```

## 状态与记忆

Agent 不能只靠聊天上下文记住业务对象。

最小结构化状态：

```json
{
  "conversation_id": "...",
  "user_context": {
    "erpnext_user": "...",
    "role_profile": "采购员",
    "company": "STEC (Demo)"
  },
  "active_entities": {
    "current_project": "PROJ-0010",
    "last_material_request": "MAT-MR-2026-00003"
  },
  "pending_clarifications": [],
  "pending_confirmations": [],
  "last_tool_calls": [],
  "last_tool_results": []
}
```

需要写入记忆的内容：

- 最近创建或打开的 MR、PO、PR、PI、Stock Entry
- 用户刚确认过的物料候选
- 当前项目、仓库、供应商
- 待追问字段
- 待提交草稿
- ToolCall 与 ToolResult 审计链路

## 和 LangGraph / MCP 的关系

这套方案不排斥 LangGraph 或 MCP，但不能依赖它们解决核心问题。

推荐边界：

```text
LangGraph:
  管多步业务流程状态，例如申请 -> 下单 -> 收货 -> 开票

MCP:
  把稳定工具和业务入口暴露给不同 Agent 客户端

Parameter Orchestrator:
  独立核心模块，负责把业务意图编译成 ToolCall
```

也就是说：

```text
LangGraph 节点可以调用参数编排层。
MCP tool handler 也可以调用参数编排层。
参数编排层不应该被某个 Agent 框架锁死。
```

## v0.1 落地范围

第一版不要一次覆盖 150 个 ToolCall。先做一条竖线：

```text
自然语言材料申请
  -> 意图草稿
  -> 物料/项目/仓库/日期 Resolver
  -> 参数编排
  -> ToolGateway
  -> ERPNext 创建 Material Request 草稿
  -> 返回人话摘要
```

必须支持的输入：

```text
明天合流1.3标要 100 双帆布手套，送项目仓。
```

必须输出：

- 结构化意图草稿
- Resolver 查询结果
- 缺失字段或候选歧义
- 最终 ToolCall JSON
- ERPNext 创建结果
- 人话摘要
- 审计记录

第二批再扩展：

1. 采购订单草稿
2. 采购收货
3. 项目领料
4. 库存查询
5. 应付查询

## 新增 ToolCall 的接入规则

以后每新增一个 ToolCall，必须同时补齐：

```text
1. JSON Schema
2. ToolCall Contract
3. allowed_roles / expose / risk / confirm
4. parameter_plan
5. backend_mapping
6. resolver 依赖
7. validator 规则
8. repair / clarification 策略
9. 至少一个单元测试
10. 如果是关键业务动作，要有模拟模型序列和本地 ERPNext 集成验收用例
```

如果一个 ToolCall 的字段需要 ERPNext 主数据，就必须声明 Resolver；如果无法声明 Resolver，就不应该直接暴露给员工 Agent。

## 最终目标

最终系统应该形成这样的稳定模式：

```text
员工说人话
  -> 模型理解意图
  -> Runtime 查已有数据
  -> Contract 指导字段怎么填
  -> Resolver 找真实 ERPNext ID
  -> Validator 拦截坏参数
  -> Gateway 控制工具和身份
  -> ERPNext 执行业务规则
  -> Memory 记录业务状态
  -> Agent 用人话解释结果
```

这就是本项目从“ERPNext ToolCall 工具库”升级为“企业员工 Agent 工作平台”的关键路径。
