# ADR-002：OpenClaw 采用渐进式说明书

- 状态：accepted
- 决策：OpenClaw 负责交流和规划，Nexterp 按需搜索能力并加载当前节点说明书。
- 原因：不把全部 Tool schema 和业务字段一次塞给模型，降低选择错误和上下文噪声。
- 影响：模型不能自行拼底层 ToolCall；Capability API 返回紧凑能力卡和当前 Guide。
