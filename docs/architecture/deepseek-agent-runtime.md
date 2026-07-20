# DeepSeek 自主规划 Runtime

## 目标

员工自然语言由 DeepSeek 自主拆解为连续动作。Runtime 不使用关键词路由。对于采购写操作，DeepSeek 输出有限的结构化业务目标，由业务能力层根据 ERPNext 实时状态编译成 ToolCall；模型不再直接承担事务编排。

```text
用户 -> DeepSeek 动作 -> 工具发现/契约/Resolver -> ToolGateway -> ERPNext -> DeepSeek
```

## 动作协议

模型每轮只返回一种 JSON 动作：

- `discover_tools`：从当前岗位可用工具中检索紧凑工具卡。
- `get_tool_contracts`：按需读取最多五个完整工具契约。
- `resolve_entities`：核对物料、项目、仓库、供应商、公司、员工、日期、单位或单据。
- `propose_business_action`：提交结构化业务意图，由确定性能力图和编译器生成采购 ToolCall。
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
- 业务写操作的确认绑定到规范化 ToolCall 摘要，确认后参数变化会自动取消执行。
- 执行成功后重新读取 ERPNext 单据，核对单号、类型和来源行关系。
- `request_id` 防止重复执行。

旧 `CivilAgentRuntime` 作为 `LegacyCivilAgentRuntime` 仅供回归测试。默认 `CivilAgentRuntime` 是 `DeepSeekAgentRuntime` 的兼容名称。

### 候选物料库存补全

物料实体解析采用一条无缓存的请求内链路：

```text
用户描述
-> ReleaseMaterialResolver 返回候选物料
-> 收集本次动作内所有候选 item_code
-> 员工本人 ERPNext API 账号一次查询 Bin
-> 将各仓实际量、预留量、可用量和预计量合并到候选
-> DeepSeek 比较候选并向员工推荐
```

当前相关仓库限定为所选项目仓和蕰川路基地仓库。查询结果只存在于本轮 observation，
不写入物料检索缓存或库存缓存。用户提供需求数量和单位时，候选结果同时计算库存缺口；
单位不一致时不自动换算缺口。

## 审计

每轮保存当前项目、仓库、已确认实体、历史单号、待确认动作和 Agent 步骤。网页只展示可审计的动作摘要、参数和 observation，不展示模型隐藏思维过程。

业务能力层的详细边界和采购能力清单见 [业务能力 Runtime](business-capability-runtime.md)。
