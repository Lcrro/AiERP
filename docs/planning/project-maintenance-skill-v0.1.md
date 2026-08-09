# 项目整理与上下文维护 v0.1

本阶段只整理工程结构、状态入口、文档边界和 Codex Skill，不重构 Agent、ERPNext Adapter 或物料业务逻辑。

## 交付物

- `config/project_context.yaml`：机器可读的长期项目状态。
- `scripts/dev/project_context.py`：恢复摘要、快照、文档审计、状态和交接。
- `scripts/dev/install_project_skill.py`：跨 Windows/WSL 安装项目 Skill。
- `skills/nexterp-project-maintainer/`：短规约和按需参考。
- `docs/architecture/current-system.md`、`docs/decisions/`、`docs/handoffs/current.md`：当前入口。

## 验收

- `resume` 输出小于 8 KB。
- `check` 不读取凭据，检查文档断链和状态文档长度。
- 项目维护 Skill 可以安装到临时 `CODEX_HOME`，本地修改不会被无提示覆盖。
- 新任务只读取恢复摘要、交接快照和本次相关模块即可继续工作。
