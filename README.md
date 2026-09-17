# Nexterp Agent

Nexterp is an employee-facing assistant layer above ERPNext. The current path is:

```text
员工工作台
  -> OpenClaw + DeepSeek：理解目标、按需加载能力说明书
  -> Nexterp：身份、Resolver、预检、确认、ToolCall 编译
  -> ERPNext：权限、工作流、库存、单据和审计事实
  -> 回读结果并用人话回复
```

工作台入口是 `http://127.0.0.1:8788/`，本地 civil ERPNext 开发账套通常为
`http://localhost:8002`。服务启动方式和实际端口以项目状态与运行手册为准。

## Quick Start

安装 Python 包并运行单元测试：

```powershell
python -m venv .venv
.\\.venv\\Scripts\\python -m pip install -e ".[dev]"
python -m pytest tests/unit/item_master -q
```

恢复当前开发上下文：

```powershell
python scripts/dev/project_context.py resume
python scripts/dev/project_context.py snapshot
python scripts/dev/project_context.py check
```

复制 `.env.example` 为 `.env` 后，按运行手册启动本地服务。凭据只留在本机，不提交 Git。

## Documentation

- [文档索引](docs/README.md)
- [当前系统架构](docs/architecture/current-system.md)
- [项目状态](docs/project-status.md)
- [当前开发交接](docs/handoffs/current.md)
- [本地 Sandbox 运行说明](docs/operations/local-sandbox.md)
- [员工工作台](docs/operations/agent-workbench.md)
- [团队交接与环境恢复](docs/operations/team-handoff.md)
- [物料主数据标准](docs/reference/material-master-standard.md)
- [Capability Skill 清单](docs/reference/capability-skill-catalog.md)

历史计划、旧 Runtime 和一次性实验在 `docs/archive/2026/`，不作为新任务默认上下文。

## Repository Layout

```text
src/nexterp_agent/             Python package
  agent_runtime/               OpenClaw/DeepSeek runtime and context
  erpnext/                     ToolCall schemas, adapter, client, policy
  item_master/                 Material master, resolver, catalog, intake
  workbench/                   Employee workbench service
frappe_apps/agent_bridge/      Tracked Frappe bridge app mirror
scripts/                       Dev, ERPNext, OpenClaw and data utilities
config/                        Machine-readable project and business config
data/                          Authoritative releases and local data assets
docs/                          Active, reference, generated and archived docs
tests/                         Unit, integration, acceptance and evaluation tests
tools/                         Local viewer and lab pages
skills/                        Repository Skills, including project maintainer
```

开发约束见根目录 [AGENTS.md](AGENTS.md)。
