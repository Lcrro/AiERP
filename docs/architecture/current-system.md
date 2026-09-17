# 当前系统架构

## 真实运行链路

```text
员工工作台
  -> OpenClaw + DeepSeek：交流、理解目标、按需加载说明书
  -> Nexterp Capability API：身份、Resolver、字段来源、预检、确认冻结
  -> ToolGateway / ERPNext Adapter：按员工身份执行 ToolCall
  -> ERPNext/Frappe：权限、工作流、库存、单据和审计事实
  -> 回读 ERPNext 结果
  -> 工作台展示助理回复、单据和可审计步骤
```

## 入口

| 入口 | 用途 |
| --- | --- |
| `http://127.0.0.1:8788/` | 员工工作台正式入口 |
| `http://127.0.0.1:8788/material-intake-lab` | 批量采购清单准入实验室 |
| `http://127.0.0.1:8788/material-item-lab` | 自然语言新增标准物料实验室 |
| `http://127.0.0.1:8788/procurement-batch-pilot` | 龙华实际采购清单前 100 行本地批处理与边界项审阅台；可冻结规则，不写 ERPNext |
| `http://127.0.0.1:8790` | Capability API |
| `http://localhost:8002` | civil ERPNext 开发账套 |

## 边界

- ERPNext 是权限、工作流、库存和单据状态的唯一事实来源。
- OpenClaw 不持有 ERPNext 密钥，不直接选择底层 ToolCall。
- Nexterp 负责可信员工身份、项目情境、说明书、实体解析、确定性编译、预检、确认和回读。
- 业务写入必须使用员工本人身份、明确确认、幂等 `request_id`，执行后回读验证。
- 工作台不维护第二套库存、审批或单据状态；页面只读取 ERPNext 当前结果。
- 采购清单批处理属于 ERPNext 发布前的本地候选、审阅与内部参考工作台层。逐项结论绑定源候选哈希；冻结后的实际组合可原子发布到本机 GPC 工作台运行期资料，但不创建 ERPNext 物料，也不构成 ERPNext 业务写入确认。版本化规则继续影响后续 GPC 候选检索与错误编码拦截。
- GPC 是只读参考目录。确无合适官方 Brick 或需要施工采购细分时，采用版本化扩展层级；官方 8 位编码不变，每新增一层在父编码后追加两位 `01–99`。内部节点以 `is_gpc=false`、`catalog_origin=nexterp` 和 `classification_source=nexterp_internal` 隐性标识，不计入官方 GPC 数量，也不得导出或冒充 GS1 编码。
- 参考目录工作台的本机运行时事实保存在 `.runtime/material-master/reference-catalog.sqlite3`。官方 GPC、内部末级、属性和值、实际物料及采购类型档案分表保存；官方来源包仍保留为可重复导入的 JSON/JSONL。业务表触发器推进目录 `revision`，8788 页面只读轮询 revision 并局部重载，不提供浏览器任意 SQL 接口，也不改变 ERPNext 的权威边界。

## 代码定位

- 工作台：`src/nexterp_agent/workbench/`、`tools/workbench/`
- Agent Runtime：`src/nexterp_agent/agent_runtime/`
- 物料：`src/nexterp_agent/item_master/`
- ToolCall 与 Adapter：`src/nexterp_agent/erpnext/`
- Capability API：`src/nexterp_agent/capability_service/`
- OpenClaw 集成：`scripts/openclaw/`、`frappe_apps/agent_bridge/`

## 无头 ERPNext 物料投影

完整 GPC 目录、Nexterp 扩展层级、属性和审阅事实继续保存在参考目录数据库，不复制成 ERPNext 的深层 `Item Group`。独立测试 Site `material-test.localhost` 只保存少量经营组、UOM 和已确认 SKU；Item 通过源记录 ID、标准类型编码、GPC Brick、分类路径、目录 revision 和源哈希回链 Nexterp。

发布由固定测试 Site 的受控命令执行：先生成只读 diff，再确认不可变 `release_hash` 与幂等 `request_id`，通过标准 Frappe REST 写入，最后逐 Item GET 回读。ERPNext 继续负责 Item 是否存在、库存与业务单据事实；参考目录数据库继续负责任意层级分类与检索。详见 [GPC 到 ERPNext 物料测试账套同步 v0.1](../reference/gpc-erpnext-material-test-sync-v0.1.md)。

详细历史方案保留在归档目录；本文件只描述当前真实运行边界。
