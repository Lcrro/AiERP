# 项目状态

更新日期：`2026-07-13`

## 当前基线

- 分支：`codex/civil-agent-v1.0`
- ERPNext 开发账套：`http://localhost:8002`
- 员工 Agent 工作台：`http://127.0.0.1:8788/`
- Tool schema 与 Adapter handler：`150 / 150`
- 主数据来源：`data/master_data/` 与 `data/material_master/`
- Agent 主入口：`DeepSeekAgentRuntime`
- 测试：`223 passed, 3 skipped`

## 已具备

- ERPNext/Frappe API 认证、通用文档操作和五大模块 ToolCall。
- Tool Contract、按岗位工具暴露、员工身份 ToolGateway 和写操作确认。
- 物料四级发布表、物料 Resolver 和 PostgreSQL 目录能力。
- 公司、组织、员工、项目、仓库、供应商、价格等基础主数据发布包。
- DeepSeek 自主规划循环、工具发现、契约查询、实体解析和多轮会话。
- 候选物料检索后，一次查询相关仓库实时库存并合并给 Agent 推荐。
- 独立 ERPNext 开发账套的主数据 `plan/apply/verify` 导入流程。

## 数据状态

- 当前 UP 事业部项目、员工、仓库和物料主数据保留。
- 历史业务模拟的脚本、报告、网页、会话和 ERPNext 交易记录已清理。
- ERPNext 中对应旧仓库、项目、供应商、账号、库存台账和删除审计记录均为零。
- Runtime 会话目录已重置，员工下次操作会建立新会话。

## 下一步

1. 在工作台重新验证“用户描述 -> 候选物料 -> 相关仓库实时库存 -> Agent 推荐”。
2. 验证候选选择后生成材料申请草稿，并检查确认与幂等行为。
3. 再逐条验证采购订单、采购收货、退货、发票和项目领料。
4. 为每条真实链路补可重复清理的集成测试数据标记。

## 维护规则

- 权威主数据只从发布目录导入，不从 Runtime 会话反向生成。
- 集成测试产生的交易单据必须可识别、可清理。
- Link 字段必须由 Resolver 或 ERPNext 真实结果提供。
- 所有写操作使用员工本人凭据并先确认。
- 临时报告和会话只能放在 `data/runtime/`，不提交业务测试记录。
