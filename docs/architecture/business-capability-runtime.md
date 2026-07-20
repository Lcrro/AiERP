# 业务能力 Runtime

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

财务和项目的其他业务按相同方式增加独立能力包，不把所有模块塞进一个总提示词。

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
