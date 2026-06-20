# 文档索引

这个项目使用轻量文档结构，参考了 Diataxis 的分类思路：

```text
overview      从哪里开始、项目里有什么
architecture  系统架构、模块关系和长期路线
reference     稳定事实，例如 API、schema、ToolCall、规则
planning      分版本计划、开发清单和验收标准
operations    本地运行、验证、维护和排障
scenarios     业务沙盘、角色、流程样例
```

目标是让每个文档只回答一类问题，避免所有内容混在一起。

## 从这里开始

- [项目 README](../README.md)：项目根目录的简短入口。
- [项目状态](project-status.md)：当前分支、覆盖数量、测试状态和下一步队列。
- [当前 Codex 对话压缩上下文](project-thread-context-2026-06-20.md)：本轮长期对话的关键决策、实现状态和下一步建议。
- [架构路线图](architecture/roadmap.md)：分阶段架构目标。
- [Tool Layer v0.1 清单](planning/tool-layer-v0.1.md)：后端工具层工作队列。
- [物料主数据与检索 v0.1 计划](planning/item-master-search-v0.1.md)：物料表和检索工作队列。

## 架构

- [架构路线图](architecture/roadmap.md)
- [项目结构与解耦边界](architecture/project-structure.md)
- [DocType 索引与 Agent 上下文](architecture/doctype-index.md)
- [ToolCall 参数编排层设计](architecture/toolcall-parameter-orchestration.md)

架构文档回答“系统应该长什么样，以及为什么这样设计”。

## 计划

- [ERPNext Tool Layer v0.1](planning/tool-layer-v0.1.md)
- [ERPNext Tool Layer v0.2 模块覆盖](planning/tool-layer-v0.2-module-coverage.md)
- [物料主数据与检索 v0.1](planning/item-master-search-v0.1.md)

计划文档是按版本组织的工作队列，应该包含开发清单、验收标准和下一步任务。

## 运行与维护

- [本地 Sandbox 运行说明](operations/local-sandbox.md)
- [物料目录 PostgreSQL 运行说明](operations/material-catalog-postgres.md)

运行文档回答“本地系统怎么启动、怎么验证、怎么维护”。

## 业务场景

- [小型土木公司一日运转模拟：员工角色表](scenarios/civil-company-day-roles.md)
- [小型土木公司一日运转模拟：时间顺序事件流](scenarios/civil-company-day-events.md)
- [小型土木公司一日运转模拟：ToolCall 覆盖矩阵](scenarios/civil-company-day-toolcall-coverage.md)
- [小型土木公司一日运转模拟：Sandbox 初始化](scenarios/civil-company-day-seed.md)
- [小型土木公司一日运转模拟：一天事件流准备度](scenarios/civil-company-day-readiness.md)
- [小型土木公司一日运转模拟：执行记录](scenarios/civil-company-day-execution-log.md)
- [Wizard of Oz ToolCall 手动测试](scenarios/wizard-of-oz-testing.md)
- [DeepSeek 材料申请 ToolCall 试验](scenarios/deepseek-material-request-trial.md)
- [DeepSeek 材料申请试验输入输出记录](scenarios/deepseek-material-request-io-log.md)

业务场景文档回答“系统要服务哪些人、他们在真实业务中怎么协作”。

## 参考

- [ERPNext 能力地图](reference/erpnext-capability-map.md)
- [物料主数据标准](reference/material-master-standard.md)
- [ERPNext 物料检索工具](reference/item-search-tool.md)
- [采购清单物料标准化归档](reference/purchase-material-standardization.md)
- [采购清单整理后的标准物料目录](reference/standard-item-catalog-from-review.md)
- [物料主数据 SKU 草案 v0.3](reference/material-item-master-draft-v0.3.md)
- [物料目录 PostgreSQL 层](reference/material-catalog-postgres.md)
- [当前 ToolCall 清单](reference/toolcall-current-inventory.md)
- [ToolCall Data Dictionary 设计稿](reference/toolcall-data-dictionary.md)
- [ToolCall 用户与权限](reference/toolcall-users-permissions.md)
- [ToolCall 五大模块控制矩阵](reference/toolcall-five-module-control-matrix.md)
- [ToolCall 资产](reference/toolcall-assets.md)
- [ToolCall 库存](reference/toolcall-stock.md)
- [ToolCall 采购](reference/toolcall-buying.md)
- [ToolCall 项目专项](reference/toolcall-projects.md)
- [ToolCall 财务](reference/toolcall-accounting.md)

当 schema、工具契约、API 行为或业务规则已经比较稳定时，把它们放到参考文档里。

计划中的参考文档：

```text
docs/reference/tool-contracts.md
docs/reference/agent-bridge-api.md
docs/reference/configuration.md
```

## 文档规则

- 根目录 `README.md` 保持简短。
- 长架构说明和设计材料放到 `docs/architecture/`。
- 分版本任务清单放到 `docs/planning/`。
- 运行手册和排障说明放到 `docs/operations/`。
- 业务沙盘、角色表和流程样例放到 `docs/scenarios/`。
- 稳定的 schema、工具契约和 API 细节放到 `docs/reference/`。
- 不提交生成缓存、密钥或真实 ERPNext 业务数据。
- 优先使用链接，不重复粘贴同一份内容。
