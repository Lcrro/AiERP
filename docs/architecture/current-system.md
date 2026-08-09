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
| `http://127.0.0.1:8790` | Capability API |
| `http://localhost:8002` | civil ERPNext 开发账套 |

## 边界

- ERPNext 是权限、工作流、库存和单据状态的唯一事实来源。
- OpenClaw 不持有 ERPNext 密钥，不直接选择底层 ToolCall。
- Nexterp 负责可信员工身份、项目情境、说明书、实体解析、确定性编译、预检、确认和回读。
- 业务写入必须使用员工本人身份、明确确认、幂等 `request_id`，执行后回读验证。
- 工作台不维护第二套库存、审批或单据状态；页面只读取 ERPNext 当前结果。

## 代码定位

- 工作台：`src/nexterp_agent/workbench/`、`tools/workbench/`
- Agent Runtime：`src/nexterp_agent/agent_runtime/`
- 物料：`src/nexterp_agent/item_master/`
- ToolCall 与 Adapter：`src/nexterp_agent/erpnext/`
- Capability API：`src/nexterp_agent/capability_service/`
- OpenClaw 集成：`scripts/openclaw/`、`frappe_apps/agent_bridge/`

详细历史方案保留在归档目录；本文件只描述当前真实运行边界。
