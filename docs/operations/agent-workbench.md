# 员工工作台

员工工作台是 ERPNext 上方的简化业务入口。当前正式助理使用隔离的 OpenClaw + DeepSeek 渐进式说明书 Runtime；OpenClaw 负责交流和规划，Nexterp 负责能力说明书、实体解析、确定性编译、确认和执行，ERPNext 仍负责数据、权限、工作流和审计。

## 启动

先启动独立 ERPNext sandbox：

```powershell
.\scripts\dev\start_wsl_sandbox.ps1
```

再启动工作台：

```powershell
python scripts\dev\agent_workbench.py --port 8788 --profile civil
```

打开 `http://127.0.0.1:8788/`。

## 页面结构

- 左侧选择项目和员工测试身份。
- 中间是按“员工 + 项目 + 会话”隔离并持久化的工作助理。
- 右侧“我的工作”显示 ERPNext 的审批待办、本人申请、采购进度、最近单据和异常退回。
- 单据在工作台抽屉中打开，不跳转 ERPNext；普通员工不显示 ToolCall 和 JSON。
- “开发者模式”用于查看 Agent 步骤、ToolCall、ToolResult 和完整 JSON。

## 操作规则

自然语言请求通过 OpenClaw 渐进式说明书 Runtime。Agent 先搜索业务能力，再按需加载当前节点 Guide，不会一次取得全部底层 ToolCall。物料多候选时，工作台展示名称、关键规格、单位和相关仓库实时库存，点击卡片会发送结构化选择事件。

所有 Agent 写操作先由 Nexterp `prepare` 生成冻结的 `pending_id`，工作台展示业务摘要并等待确认。确认按钮直接执行这一份冻结动作，不再次调用模型规划；员工、项目、会话、目录版本和 ToolCall 哈希不匹配时拒绝执行。`request_id` 防止重复写入。

明确的提交、批准和驳回按钮不调用 DeepSeek，直接使用当前员工的 ERPNext 身份执行原生工作流动作。右侧“待我处理”直接读取 ERPNext `Workflow Action`，工作台不维护第二套审批状态。

会话按“员工 + 项目 + conversation_id”隔离，并映射为持久 OpenClaw 会话。刷新页面会恢复当前会话；“新会话”只清理当前项目和员工的对话、已解析实体和待确认操作，不删除 ERPNext 单据。旧 Runtime 的本地会话使用不同命名空间，不会污染新版 Agent。

旧 Nexterp Runtime 不再承接工作台正式请求，只在 `/agent-runtime-compare` 中按需启用，作为 A/B 回归基线。

## 接口

```text
GET  /api/workbench/bootstrap
GET  /api/inbox
GET  /api/documents
GET  /api/document
POST /api/workflow/action
POST /api/document/submit
POST /api/agent/turn
POST /api/agent/confirm
POST /api/session/reset
```

旧 `/api/agent` 在迁移期继续兼容。

## 当前采购流程

第一版覆盖材料申请、审批、询价、采购订单、采购收货和采购退货的读取及单据卡。材料申请审批为：

```text
材料员提交申请
-> 材料设备主管批准或驳回
-> 项目经理批准或驳回
-> ERPNext 正式提交
```

审批通知、Workflow Action 和操作记录均以 ERPNext 为准。

## 采购闭环验收

先加载 `.env` 并确保 ERPNext 开发账套运行，再执行：

```powershell
python scripts\acceptance\procurement_closed_loop.py prepare
python scripts\acceptance\procurement_closed_loop.py all
```

也可以分别运行 `run`、`verify` 和 `cleanup`。`all` 会依次准备、创建采购闭环、验证来源关系和库存回零，并清理测试交易。ERPNext 因总账或库存账审计关系不允许删除的交易会保留为已取消单据，这是正常的审计行为。
