# OpenClaw 渐进式说明书 Runtime v0.5

## 目标

本实验验证 OpenClaw 是否适合作为员工助理的交流和规划外壳，同时把 ERPNext 业务约束继续留在 Nexterp 内部：

```text
OpenClaw + DeepSeek
  -> 搜索业务能力
  -> 按需加载节点说明书
  -> 提交结构化业务事实
  -> Nexterp 解析、校验和编译
  -> 用户确认冻结动作
  -> ERPNext 以员工身份执行
  -> Nexterp 回读真实结果
```

当前已覆盖采购主链的六个写操作：创建材料申请草稿、从材料申请询价、从询价录入供应商报价、从报价创建采购订单、从订单创建采购收货、从收货创建采购退货。旧 Runtime 已在对比页默认关闭，仅按需作为回归基线。

## 组件边界

### OpenClaw

负责：

- 与员工自然交流；
- 判断当前需要搜索或加载什么能力；
- 从用户原话提取项目、物料描述、数量和日期；
- 根据 Nexterp 返回的缺失信息或候选继续追问；
- 用真实执行结果生成员工可读回复。

不负责：

- 编造 ERPNext Link 主键；
- 直接拼底层 ToolCall；
- 自行决定员工身份和权限；
- 修改已进入确认阶段的 ToolCall；
- 把库存、审批状态或单据状态写入长期记忆。

### Nexterp Capability API

负责：

- 从 PostgreSQL 检索能力节点和说明书；
- 根据可信请求头绑定 OpenClaw 会话与 ERPNext 员工；
- 调用 Resolver 获取真实项目、仓库、物料和单位；
- 填充系统默认值，执行规则校验并确定性编译 ToolCall；
- 生成绑定会话、员工、项目、目录版本和哈希的待确认动作；
- 执行冻结动作、保证幂等并回读 ERPNext 结果。

### ERPNext

ERPNext 仍是权限、库存、工作流、单据状态和业务数据的唯一事实来源。OpenClaw Plugin 不持有 ERPNext API Secret。

## 说明书关系模型

PostgreSQL 是 v0.5 说明书目录的唯一生产事实来源：

| 表 | 作用 |
| --- | --- |
| `capability_node` | 模块、能力、操作和字段槽位节点 |
| `capability_edge` | 节点间的包含、复用、前置和后续关系 |
| `capability_alias` | 中文名称、现场俗称和检索词 |
| `operation_tool` | 操作到内部 ToolCall、编译器和验证器的映射 |
| `operation_rule` | 跨字段和业务状态规则 |
| `external_identity` | OpenClaw 请求者与 ERPNext 员工身份绑定 |
| `catalog_revision` | 当前目录版本和内容校验值 |

数据库保存声明性说明和稳定实现键，不保存可执行代码。编译器、Resolver、预检器和回读验证器仍由 Python 实现。

## OpenClaw 工具面

新 Profile 只向模型暴露四个元工具：

```text
nexterp_search_capabilities
nexterp_load_guide
nexterp_prepare_operation
nexterp_execute_prepared_operation
```

工作区 `AGENTS.md` 和 Skill 只保存短工作规约；完整说明书通过 Capability API 渐进加载。对比会话的 `sessionKey` 包含 `:compare-preview:`，Plugin 会在工具实现和 `before_tool_call` 钩子两层禁止执行写入。

## HTTP 接口

Capability API 默认监听 `127.0.0.1:8790`：

```text
POST /api/capabilities/search
POST /api/guides/load
POST /api/operations/prepare
POST /api/operations/execute
GET  /api/operations/{pending_id}
```

身份来自 Plugin 写入的可信请求头，不接受模型在 JSON body 中提交员工邮箱。执行接口只接受服务端生成的 `pending_id`。

## 隔离运行环境

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| 员工工作台 | `http://127.0.0.1:8788/` | 现有 Runtime 基线 |
| A/B 对比页 | `http://127.0.0.1:8788/agent-runtime-compare` | 默认只运行 OpenClaw；旧版按需开启 |
| Capability API | `http://127.0.0.1:8790` | WSL 内说明书服务 |
| OpenClaw Gateway | `ws://127.0.0.1:18829` | 隔离 Profile `nexterp` |
| 旧 OpenClaw | `ws://127.0.0.1:18789` | 不由本实验修改 |

隔离 Runtime 使用项目独立 Node `22.22.3`、OpenClaw `2026.7.1-2`、状态目录 `~/.openclaw-nexterp` 和权限为 `600` 的 `~/.config/nexterp/openclaw-nexterp.env`。

## 安装与启动

在 WSL 中执行：

```bash
bash scripts/openclaw/install_nexterp_runtime.sh
bash scripts/openclaw/restart_nexterp_runtime.sh
```

单独启动组件：

```bash
bash scripts/openclaw/start_capability_api.sh
bash scripts/openclaw/start_nexterp_gateway.sh
```

从命令行调用隔离 Agent：

```bash
bash scripts/openclaw/run_nexterp_agent.sh \
  --session-id agent:nexterp:manual-test \
  --message '帮我给合流1.3标申请20包水泥，后天要用' \
  --json
```

## 当前验收状态

- PostgreSQL 迁移可重复执行；材料申请以及询价、供应商报价、采购订单、采购收货、采购退货的操作节点、槽位、规则和前后关系均已入库。
- 五项新增操作均实时读取唯一来源单据，以员工本人 ERPNext 身份校验状态和权限；公司、项目、物料、数量、单位及子表来源引用不由模型重填。
- 供应商、项目和仓库通过 Resolver 解析；部分报价、下单、收货或退货必须绑定真实来源子表行。
- 每项写操作由确定性编译器生成底层 ToolCall，确认摘要与 ToolCall 哈希冻结；执行成功后按目标 DocType、来源关系和关键字段回读验证。
- 四个 Plugin 工具、可信身份派生和预览会话写入阻断已有自动化测试。
- Capability API 已覆盖服务令牌、请求头身份和执行 body 防篡改测试。
- 真实 OpenClaw 已完成能力搜索、Guide 加载和材料申请 prepare 预览。
- Resolver 已改为复用发布版物料评分器，宽泛搜索不再按文件顺序把“水泥砖”排在“水泥”本体之前。
- A/B 页面只展示可审计动作摘要，不展示模型隐藏思维。
- A/B 页面默认暂停旧版 Runtime，后端不会调用旧模型；需要回归对照时可手动开启。新版等待期间显示“小助理正在……”和当前处理阶段。
- 物料名称使用归一化精确匹配，名称中的空格差异不会再制造假多候选。
- `prepare` 会验证用户提供的单位是否属于解析后 SKU 的真实可用单位，错误单位返回候选而不是进入确认。
- 真实 DeepSeek 预览基准 `20 / 20` 通过，执行调用为 `0`，中位耗时 `19.58s`。
- OpenClaw Control UI 已完成一次权威确认写入：审批卡展示冻结后的项目、仓库、物料、数量和日期，用户选择“允许一次”后才执行。
- ERPNext 以材料员本人身份创建并回读材料申请草稿 `MAT-MR-2026-00004`，回读字段与确认摘要一致；验收后已删除草稿并验证单据不存在。
- 非交互 CLI 不会把聊天中的“确认”当成审批决定；必须连接 Control UI 或配置支持审批的消息渠道，未确认和超时均保持零写入。
- Python 全量回归 `430 passed`；其中采购链 Capability Service 单元测试 `29 passed`，PostgreSQL 目录集成测试 `3 passed`，Plugin 测试 `4 passed`，TypeScript 构建和打包检查通过。
- 真实 Capability API 已使用 `MAT-MR-2026-00003` 完成询价预览：解析真实供应商并冻结完整来源明细，全程零 ERPNext 写入，临时待确认记录已清理。
- 真实 OpenClaw + DeepSeek 已按需搜索并逐层加载五项新增能力，能正确说明“材料申请 -> 询价 -> 供应商报价 -> 采购订单 -> 采购收货 -> 可选退货”，且只暴露四个元工具。
- 隔离 Runtime 重启脚本会同时清理 PID 文件和专用端口上的残留进程，并等待服务最多 30 秒，避免代码升级后仍连接旧 Capability API。

## 后续扩展门槛

下一阶段先为五项新增操作补齐连续真实单据链验收和稳定性基准，再把同一说明书模式扩展到库存调拨、项目领料和财务结算。
