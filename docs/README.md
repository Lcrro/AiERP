# 文档索引

这里是 Nexterp 的短入口。新任务先看当前系统、项目状态和交接快照，再按请求读取一个或少量模块文档。

## 从这里开始

- [项目 README](../README.md)
- [当前系统架构](architecture/current-system.md)
- [项目状态](project-status.md)
- [当前开发交接](handoffs/current.md)
- [本地 Sandbox 运行说明](operations/local-sandbox.md)
- [员工工作台](operations/agent-workbench.md)
- [分层测试策略](operations/testing-strategy.md)

## 当前架构

- [架构路线图](architecture/roadmap.md)
- [项目结构与解耦边界](architecture/project-structure.md)
- [OpenClaw 渐进式说明书 Runtime](architecture/openclaw-progressive-manual-runtime.md)
- [Capability Skill 清单](reference/capability-skill-catalog.md)
- [基础主数据标准](reference/master-data-standard.md)
- [ERPNext 能力地图](reference/erpnext-capability-map.md)

## 设计决策

- [ADR 索引](decisions/README.md)

## 稳定参考

- [物料主数据标准](reference/material-master-standard.md)
- [物料检索工具](reference/item-search-tool.md)
- [材料申请审批流程](reference/material-request-approval-workflow.md)
- [当前 ToolCall 清单](reference/toolcall-current-inventory.md)
- [ToolCall Data Dictionary](reference/toolcall-data-dictionary.md)
- [ToolCall 五大模块控制矩阵](reference/toolcall-five-module-control-matrix.md)
- [物料目录 PostgreSQL 层](reference/material-catalog-postgres.md)
- [批量采购物料准入 Skill](reference/batch-material-intake-skill.md)
- [物料批量高召回检索 v0.6](reference/material-high-recall-v0.6.md)
- [物料接入第八步：录入草稿 v0.7](reference/material-intake-draft-step-v0.7.md)
- [物料准入闭环 v0.8：确认、发布与 ERPNext 回读](reference/material-intake-publish-v0.8.md)
- [GPC 物料目录统一六层结构 v0.5](reference/gpc-uniform-six-level-hierarchy-v0.5.md)
- [物料分类与录入规则 v1.1：1979 条 SKU 全量重建](reference/material-entry-rules-v1.1.md)
- [施工采购模板与稀疏 SKU 框架 v0.1](reference/procurement-template-framework-v0.1.md)
- [龙华实际采购清单批处理试验 v0.1](reference/procurement-batch-pilot-v0.1.md)
- [GPC 2026-05 参考目录整合 v0.1](reference/gpc-reference-catalog-v0.1.md)

## 文档分类

```text
active       当前生产路径和正在实施的方案
reference    稳定接口、规则、数据字典和业务口径
historical   已完成计划、旧架构和一次性实验
generated    可由代码或数据库重新生成的文档
```

历史资料在 [docs/archive/2026](archive/2026/) 中，只用于追溯，不进入默认上下文。生成文档不作为手工事实来源。

## 维护入口

```powershell
python scripts/dev/project_context.py resume
python scripts/dev/project_context.py snapshot
python scripts/dev/project_context.py audit-docs
python scripts/dev/project_context.py check
```

阶段结束或交接时：

```powershell
python scripts/dev/project_context.py checkpoint --write
python scripts/dev/project_context.py handoff --write
```

维护规约见根目录 [AGENTS.md](../AGENTS.md)。不要把 `.env`、`.secrets`、`data/runtime/` 或真实 ERPNext 凭据加入上下文和提交。
