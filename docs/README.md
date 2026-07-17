# 文档索引

这个项目使用轻量文档结构，参考了 Diataxis 的分类思路：

```text
overview      从哪里开始、项目里有什么
architecture  系统架构、模块关系和长期路线
reference     稳定事实，例如 API、schema、ToolCall、规则
planning      分版本计划、开发清单和验收标准
operations    本地运行、验证、维护和排障
```

目标是让每个文档只回答一类问题，避免所有内容混在一起。

## 从这里开始

- [项目 README](../README.md)：项目根目录的简短入口。
- [项目状态](project-status.md)：当前分支、覆盖数量、测试状态和下一步队列。
- [架构路线图](architecture/roadmap.md)：分阶段架构目标。
- [Tool Layer v0.1 清单](planning/tool-layer-v0.1.md)：后端工具层工作队列。
- [物料主数据与检索 v0.1 计划](planning/item-master-search-v0.1.md)：物料表和检索工作队列。
- [土木进销存 Agent v1.0](planning/civil-agent-v1.0.md)：当前产品主线、交付阶段和验收口径。
- [采购闭环与员工工作台 v0.3](planning/procurement-closed-loop-v0.3.md)：从材料申请到收货退货的实施顺序和验收标准。
- [库存调拨与项目领料 v0.4](planning/stock-movement-project-issue-v0.4.md)：采购收货后从基地仓到项目仓和项目成本的库存闭环。
- [基础主数据标准](reference/master-data-standard.md)：公司、组织、员工、项目、仓库、供应商等非物料主数据口径。

## 架构

- [架构路线图](architecture/roadmap.md)
- [项目结构与解耦边界](architecture/project-structure.md)
- [DocType 索引与 Agent 上下文](architecture/doctype-index.md)
- [Agent 使用 ToolCall 的统一方案](architecture/agent-toolcall-usage-strategy.md)
- [ToolCall 参数编排层设计](architecture/toolcall-parameter-orchestration.md)
- [DeepSeek 自主规划 Runtime](architecture/deepseek-agent-runtime.md)

架构文档回答“系统应该长什么样，以及为什么这样设计”。

## 计划

- [ERPNext Tool Layer v0.1](planning/tool-layer-v0.1.md)
- [ERPNext Tool Layer v0.2 模块覆盖](planning/tool-layer-v0.2-module-coverage.md)
- [物料主数据与检索 v0.1](planning/item-master-search-v0.1.md)
- [土木进销存 Agent v1.0](planning/civil-agent-v1.0.md)
- [采购闭环与员工工作台 v0.3](planning/procurement-closed-loop-v0.3.md)
- [库存调拨与项目领料 v0.4](planning/stock-movement-project-issue-v0.4.md)

计划文档是按版本组织的工作队列，应该包含开发清单、验收标准和下一步任务。

## 运行与维护

- [本地 Sandbox 运行说明](operations/local-sandbox.md)
- [员工 Agent CLI](operations/agent-cli.md)
- [员工工作台](operations/agent-workbench.md)
- [物料目录 PostgreSQL 运行说明](operations/material-catalog-postgres.md)

运行文档回答“本地系统怎么启动、怎么验证、怎么维护”。

## 参考

- [ERPNext 能力地图](reference/erpnext-capability-map.md)
- [物料主数据标准](reference/material-master-standard.md)
- [基础主数据标准](reference/master-data-standard.md)
- [材料申请审批流程](reference/material-request-approval-workflow.md)
- [ERPNext 物料检索工具](reference/item-search-tool.md)
- [采购清单物料标准化归档](reference/purchase-material-standardization.md)
- [采购清单整理后的标准物料目录](reference/standard-item-catalog-from-review.md)
- [物料主数据 SKU 草案 v0.3](reference/material-item-master-draft-v0.3.md)
- [物料主数据目录说明](../data/material_master/README.md)
- [物料标准类目表 v0.1](reference/material-category-taxonomy-v0.1.md)
- [物料族候选词清单](reference/material-family-candidate-terms.md)
- [物料三级名称治理规定 v0.1](reference/material-third-layer-governance-v0.1.md)
- [物料 SKU 治理提示词 v0.3](reference/material-sku-governance-prompt-v0.3.md)
- 物料主数据浏览器当前支持四级查看：`一级类目 -> 物料族 -> 物料名称 -> SKU 明细`。三级名称人工预览由 `scripts/material_master/build_third_layer_mapping_preview.py` 生成；批量治理工作包由 `scripts/material_master/build_third_layer_work_batches.py` 生成，队列在 `data/material_master/governance_v0_2/third_layer_work_queue.tsv`。
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
- 稳定的 schema、工具契约和 API 细节放到 `docs/reference/`。
- 不提交生成缓存、密钥或真实 ERPNext 业务数据。
- 优先使用链接，不重复粘贴同一份内容。
