# DeepSeek 自主规划 Runtime

## 目标

员工自然语言由 DeepSeek 自主拆解为连续动作。Runtime 不使用关键词路由、固定意图枚举或按业务意图编写的 `if/elif` 流程。

```text
用户 -> DeepSeek 动作 -> 工具发现/契约/Resolver -> ToolGateway -> ERPNext -> DeepSeek
```

## 动作协议

模型每轮只返回一种 JSON 动作：

- `discover_tools`：从当前岗位可用工具中检索紧凑工具卡。
- `get_tool_contracts`：按需读取最多五个完整工具契约。
- `resolve_entities`：核对物料、项目、仓库、供应商、公司、员工、日期、单位或单据。
- `execute_tool`：提出一个已读取契约且通过主键与 Schema 校验的 ToolCall。
- `ask_user`：候选不唯一或关键信息缺失时追问。
- `finish`：依据真实 ToolResult 生成最终回复。

一次请求最多运行十步。模型 JSON 错误重试一次，ToolCall 参数错误允许模型修复两次。达到上限、DeepSeek 不可用、身份不一致或 ERPNext 权限拒绝时明确失败，不回退规则 Runtime。

## 执行边界

DeepSeek 负责理解、规划、选工具和解释结果。以下能力保持确定性：

- ToolContract 与 JSON Schema 参数校验。
- Resolver 返回真实 ERPNext 主键和候选。
- ToolAccessPolicy 控制 Agent 可见工具。
- ToolGateway 核对员工 API 身份。
- ERPNext 执行最终角色权限和业务校验。
- 所有写操作保存为 `pending_action`，用户确认后执行原 ToolCall。
- `request_id` 防止重复执行。

旧 `CivilAgentRuntime` 作为 `LegacyCivilAgentRuntime` 仅供回归测试。默认 `CivilAgentRuntime` 是 `DeepSeekAgentRuntime` 的兼容名称。

## 审计

每轮保存当前项目、仓库、已确认实体、历史单号、待确认动作和 Agent 步骤。网页只展示可审计的动作摘要、参数和 observation，不展示模型隐藏思维过程。
