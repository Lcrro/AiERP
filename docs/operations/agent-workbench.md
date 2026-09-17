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
- 发送自然语言后，工作台立即显示“小助理正在……”状态；后台运行期间通过运行编号轮询连接、理解、能力发现、说明书读取、实体查询和操作准备等阶段，完成后再显示真实回复。阶段提示用于告知当前处理进度，完整审计步骤以最终结果中的 Agent 步骤为准。

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
POST /api/agent/turn/start
GET  /api/agent/run
POST /api/agent/turn
POST /api/agent/confirm
POST /api/session/reset
```

旧 `/api/agent` 在迁移期继续兼容。

物料准入实验室 `/material-intake-lab` 另提供：

```text
POST /api/material-intake/analyze
POST /api/material-intake/drafts
POST /api/material-intake/drafts/revise
POST /api/material-intake/drafts/confirm
```

草稿修订只重新编译并刷新冻结预览，不写 ERPNext。确认发布必须携带稳定 `request_id` 和页面已展示的 `frozen_hash`；服务端以当前员工身份创建 Item，随后独立回读验证。详细口径见 [物料准入闭环 v0.8](../reference/material-intake-publish-v0.8.md)。

税则完整结构浏览器位于 `http://127.0.0.1:8788/tariff-taxonomy-browser`。页面按需加载五层目录，避免一次渲染 15,929 个节点；所有接口只读：

```text
GET /api/tariff-taxonomy/summary
GET /api/tariff-taxonomy/children?parent_code=S15
GET /api/tariff-taxonomy/search?q=73181510&kind=sku&limit=100
```

搜索结果携带从“类”到命中节点的完整路径，页面可以逐层展开并定位。数据源必须来自 `.runtime/tariff-extraction/` 内已通过 `hierarchy_complete` 校验、且被当前审阅包引用的 JSONL；接口不接受任意文件路径，也不写入 ERPNext。

同一页面的 GPC 模式以本机 SQLite 目录库作为运行时主源：

```powershell
python scripts\material_master\sync_reference_catalog_database.py --version 2026-05
python scripts\material_master\sync_reference_catalog_database.py --status
```

数据库固定在 `.runtime/material-master/reference-catalog.sqlite3`，不提交 Git。首次同步会先完整校验 GPC 文件包、内部扩展、实际物料和类型档案，再用单个事务写入并回读；原始 JSON/JSONL 继续作为可再生来源和兼容导出。目录业务表发生 SQL 增删改时，触发器自动推进 revision；页面每 2.5 秒读取一次下列只读接口，revision 变化时保留当前来源、搜索词、展开路径和选中项并局部重载：

```text
GET /api/reference-catalog/revision?catalog=gpc
GET /api/reference-catalog/summary?catalog=gpc
GET /api/reference-catalog/children?catalog=gpc&parent_code=...
GET /api/reference-catalog/search?catalog=gpc&q=...
GET /api/reference-catalog/profile?catalog=gpc&code=...
```

批量物料发布仍先生成兼容 JSONL 并做完整候选回读，随后在同一发布流程内同步 SQLite 的实际物料和采购类型档案；两者均只影响内部分类工作台，不创建 ERPNext Item。数据库表结构、直接数据维护边界和恢复方法见 [参考目录 SQLite 运行库 v0.1](../reference/reference-catalog-database-v0.1.md)。

龙华采购清单批处理试验台位于 `http://127.0.0.1:8788/procurement-batch-pilot`。当前固定只读实际采购清单前 100 行，历史参考表不参与；任务结果和模型调用审计保存在本地 `.runtime`，接口不会写入 ERPNext：

```text
POST /api/procurement-batch-pilot/jobs
POST /api/procurement-batch-pilot/jobs/cancel
GET  /api/procurement-batch-pilot/latest
GET  /api/procurement-batch-pilot/job?job_id=...
GET  /api/procurement-batch-pilot/result?job_id=...
```

详细边界和验收数据见 [龙华实际采购清单批处理试验 v0.1](../reference/procurement-batch-pilot-v0.1.md)。

物料商城位于 `http://127.0.0.1:8788/material-marketplace`，把已审核 GPC 实际物料组织成内部采购目录。页面支持分类、标准类型、库存单位、关键词和排序筛选，并把选中物料组成采购申请清单：

```text
GET /api/material-marketplace/catalog?q=...&segment=...&standard_type=...&stock_uom=...&sort=name&page=1&page_size=24
```

目录接口只读取已审核物料，不伪造 ERPNext 价格或库存。页面显示“参考价格尚未维护”和“项目库存申请时查询”；清单转入员工工作台后只会预填自然语言申请内容，仍须由 Nexterp 解析、生成冻结预览并等待员工明确确认，才允许写入 ERPNext。

商城左侧分类筛选会返回完整的 GPC 路径树（类目到内部标准类型末级）。展开节点只改变浏览状态；选择任意节点后，服务端按该节点及全部后代物料过滤，不写入目录或 ERPNext。

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
python scripts\acceptance\material_business_portal_e2e.py prepare
python scripts\acceptance\material_business_portal_e2e.py all
```

也可以分别运行 `run`、`verify` 和 `cleanup`。`all` 会依次准备、创建采购闭环并验证来源关系和库存回读；它会保留一套带 run_id 的完整验收链供页面审阅。需要清理时再显式执行 `cleanup --run-id ...`，ERPNext 因总账或库存账审计关系不允许删除的交易会保留为已取消单据，这是正常的审计行为。
