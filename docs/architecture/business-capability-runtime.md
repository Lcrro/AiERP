# 业务能力 Runtime

## v0.3 Capability Skill

现有 20 项能力已统一注册到 `CapabilityRegistry`。每项 Capability 都是一个按需加载的业务 Skill，包含紧凑发现卡、完整 Guide、独立 Pydantic 意图模型、Resolver 要求、来源单据、前置状态、确定性编译器和回读验证器。

```text
初始上下文：模块说明 + 元动作
-> discover_capabilities：最多 5 张岗位可用能力卡
-> get_capability_guide：最多加载 3 项完整说明
-> propose_business_action：提交已加载能力对应的强类型意图
-> Resolver / Compiler / Preflight / Confirm / Execute / Verify
```

模型初始看不到 20 个 goal、完整意图 Schema 或底层写工具。选中 Guide 后才获得该能力所需字段，避免一次注入大量相似工具。Registry 以 `ToolAccessPolicy` 过滤能力，因此发现结果不会超出当前岗位可用的底层权限。

Agent 动作和 20 项业务意图均由 Pydantic v2 校验。未知字段、非法日期、负数金额、越界百分比和非法枚举会变成简短字段级 observation，模型最多修复两次。DeepSeek 主链直接把 Registry 生成的模块级 Pydantic 执行模型交给确定性编译器，不再转回旧 dataclass 重复解析；旧对象只保留兼容导入和既有调用。用于渐进披露的聚焦 Schema 与执行模型分离，因此 Guide 不会因为安全默认字段而膨胀。

Registry 中 15 个写能力对应的底层 ToolCall 已禁止经通用 `execute_tool` 调用。模型绕过时只会收到 `capability_required`，不会执行写入。相同发现、Guide、Resolver 或只读动作连续重复时，Runtime 先返回 `no_progress`，再次重复立即终止。

### 多轮 Capability 草稿

当业务信息需要分几轮补齐时，Runtime 保存当前 Capability 的结构化草稿，而不是依赖模型从聊天文本中重新回忆整张表单。后续 `propose_business_action` 只需提交新增或修正字段，Runtime 按字段合并并重新执行 Pydantic 校验。

- 物料明细等对象数组按行合并，补数量不会丢失已确认物料编码和单位。
- 切换 Capability 或项目时立即清除旧草稿。
- 写操作确认并成功回读后清除草稿。
- 只读操作成功后清除草稿；执行失败则保留，允许下一轮修复。
- Prompt 只披露当前 Capability 草稿，不混入其他项目或能力的历史字段。

### 不可转移的确认

待确认 ToolCall 除规范化哈希外，还绑定员工、岗位、Runtime 会话 ID、浏览器 conversation、项目代码和 ERPNext 项目主键。确认有效期为 30 分钟。切换员工、项目、conversation、新建会话或超过有效期后，旧确认立即失效且不能写入 ERPNext。确认执行仍使用原始 ToolCall，不重新让模型规划。

实现位置：

```text
src/nexterp_agent/agent_runtime/action_models.py
src/nexterp_agent/agent_runtime/capability_registry.py
src/nexterp_agent/agent_runtime/deepseek_agent_runtime.py
```

## 为什么增加这一层

单纯让大模型在 150 多个 ToolCall 中自由选择、填写参数和决定业务顺序，会把四类不同问题混在一起：

- 理解员工想做什么。
- 判断当前单据允许做什么。
- 把业务字段编译成严格 ToolCall。
- 判断操作是否真的成功。

提示词无法可靠承担全部职责。正确结构是让模型负责语义，让确定性代码和 ERPNext 负责状态、约束与执行。

```text
员工自然语言
-> DeepSeek 提取结构化业务意图
-> Resolver 核对真实物料、项目、仓库、供应商和单据
-> 业务能力图根据实时单据状态列出合法下一步
-> 确定性编译器生成 ToolCall
-> ToolContract / ToolGateway / ERPNext 校验
-> 用户确认绑定到不可变 ToolCall 摘要
-> ERPNext 执行
-> Runtime 重新读取单据并核对结果
-> DeepSeek 解释结果
```

## 职责边界

### DeepSeek

- 理解口语、上下文和省略信息。
- 输出 `BusinessIntentDraft`，不直接编排采购写操作的底层 JSON。
- 在候选不唯一时组织清晰追问。
- 根据真实结果生成员工可读回复。

### Resolver

- 把别名和自然语言解析成真实 ERPNext 主键。
- 返回候选、置信度和匹配依据。
- 单号在后续使用前重新读取，历史聊天中的状态不视为事实。

### 业务能力图

- 输入实时 ERPNext 单据快照。
- 只返回当前状态合法的业务动作。
- 例如草稿报价不能比价或生成采购订单，已提交采购订单才可收货。

### 确定性编译器

- 把结构化业务意图、来源单据和当前项目上下文编译成专用 ToolCall。
- 自动保留材料申请行、询价行、报价行、采购订单行等来源关系。
- 记录字段来源：用户、Resolver、当前上下文、来源单据或系统日期。
- 在调用 Adapter 前检查数量、日期、单据类型、提交状态和报价有效期。

### ToolGateway 与 ERPNext

- ToolGateway 检查工具暴露、员工身份和确认信息。
- ERPNext 负责最终权限、工作流、库存、会计和单据业务校验。
- Runtime 不复制 ERPNext 的权限系统和审批状态。

## 确认与回读

写操作预览时，Runtime 对规范化 ToolCall 计算 SHA-256 摘要。用户确认后只执行同一份 ToolCall；数量、供应商、物料或来源单号有任何变化都会使确认失效。

成功返回后，Runtime 使用员工本人 ERPNext 客户端重新读取新单据，并核对：

- 新单据类型和单号存在。
- 返回单号与实际单据一致。
- 报价转订单时保留报价行来源。
- 订单转收货时保留采购订单行来源。

回读异常不会把已成功写入误报为未执行，但会明确提示人工检查。

## 当前采购能力

| 业务目标 | 确定性能力 |
| --- | --- |
| 新建材料申请 | `material_request.create` |
| 材料申请转询价 | `rfq.from_material_request` |
| 询价录入供应商报价 | `supplier_quotation.from_rfq` |
| 比较已提交报价 | `supplier_quotation.compare` |
| 报价转采购订单 | `purchase_order.from_supplier_quotation` |
| 材料申请直接转采购订单 | `purchase_order.from_material_request` |
| 采购订单转收货 | `purchase_receipt.from_purchase_order` |
| 收货单转采购退货 | `purchase_return.from_receipt` |

实现位于：

```text
src/nexterp_agent/agent_runtime/business_capabilities/procurement.py
```

## 当前库存能力

| 业务目标 | 确定性能力 | 确认前实时检查 |
| --- | --- | --- |
| 查询物料各仓库存 | `stock.balance.query` | Resolver 可在候选阶段批量读取相关仓库；单物料能力走实时 Bin 查询 |
| 仓库间调拨 | `stock.transfer.create` | 校验源仓与目标仓，并读取源仓可用量和目标仓现存量 |
| 项目领料 | `stock.project_issue.create` | 读取项目、成本中心和来源仓可用量，缺料时不显示写入确认 |
| 库存盘点调整 | `stock.reconciliation.create` | 校验实盘数量非负；提交库存影响仍需单独确认 |

实现位于：

```text
src/nexterp_agent/agent_runtime/business_capabilities/stock.py
```

## 当前财务能力

| 业务目标 | 确定性能力 | 关键边界 |
| --- | --- | --- |
| 查询应付账款 | `finance.accounts_payable.query` | 只读；公司和供应商必须是真实主键 |
| 收货单生成采购发票 | `finance.purchase_invoice.from_receipt` | 来源必须是已提交采购收货；供应商发票号和日期由用户提供 |
| 采购发票生成付款草稿 | `finance.supplier_payment.from_invoice` | 来源必须已提交且存在未付金额；收付款账户由 ERPNext 生成 |
| 取消冲销财务单据 | `finance.document.cancel` | 只允许白名单财务单据；必须已提交、说明原因并执行财务级确认 |

实现位于：

```text
src/nexterp_agent/agent_runtime/business_capabilities/finance.py
```

财务模型不能填写应付科目、银行科目或总账分录。付款草稿调用 ERPNext 标准付款生成方法取得会计账户和发票分配关系；取消单据由 ERPNext 执行正式取消与反向会计影响，并继续受会计期间、关联单据和员工权限约束。

## 当前项目能力

| 业务目标 | 确定性能力 | 关键边界 |
| --- | --- | --- |
| 查询项目成本上下文 | `project.cost.query` | 只读取真实 Project、Task、Stock Entry 和 Purchase Receipt |
| 查询项目异常 | `project.exceptions.query` | 按实时项目日期、任务日期、状态和进度生成异常信号，不保存第二套状态 |
| 创建项目任务 | `project.task.create` | 项目来自当前确认上下文，任务标题由用户说明，创建前确认 |
| 更新项目任务 | `project.task.update` | Task 必须实时解析，只允许状态、进度、优先级、计划日期和描述 |

实现位于：

```text
src/nexterp_agent/agent_runtime/business_capabilities/projects.py
```

同一用户轮次内，同一个只读业务目标最多执行一次。即使模型轻微改变可选参数，Runtime 也不会重复查询 ERPNext；模型只能基于第一次真实结果完成回复。

## 上下文与记忆

Runtime 将信息分成三类：

1. ERPNext 事实：单据状态、库存、权限，每次按需实时读取。
2. 结构化会话状态：当前项目、仓库、已确认实体、最近已验证业务单号。
3. 对话摘要：只提供最近少量轮次，帮助理解代词和省略表达。

模型每轮只看到最近四轮对话、最近五个已验证动作和最近八个 observation。完整审计轨迹仍保存在本地，但不重复塞回模型上下文。

## OpenClaw 边界

OpenClaw 可以在未来承担聊天渠道、长期偏好、定时任务和主动通知，但不应直接获得 150 个底层工具。它只能调用本项目提供的高层入口：

```text
prepare_business_intent
confirm_business_action
read_business_result
```

业务能力图、确认摘要、员工身份、ToolGateway 和 ERPNext 权限必须继续留在本项目内部。先把核心能力验证稳定，再评估 OpenClaw 接入，避免同时引入第二套规划、记忆和工具权限模型。
