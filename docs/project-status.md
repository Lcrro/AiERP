# 项目状态

当前里程碑：`project-maintenance-skill-v0.1`（in_progress）
当前分支：`codex/project-maintenance-skill-v0.1`，HEAD：`73d385e`

## 生产入口

- workbench: `http://127.0.0.1:8788/`
- material_intake_lab: `http://127.0.0.1:8788/material-intake-lab`
- material_item_lab: `http://127.0.0.1:8788/material-item-lab`
- capability_api: `http://127.0.0.1:8790`
- erpnext_civil: `http://localhost:8002`

## 活动模块

- **员工工作台** (`workbench`)：代码 `src/nexterp_agent/workbench, tools/workbench, scripts/dev/agent_workbench.py`；测试 `tests/unit/agent_runtime/test_agent_workbench.py, tests/unit/agent_runtime/test_openclaw_workbench.py`
- **OpenClaw 渐进式说明书 Runtime** (`agent_runtime`)：代码 `src/nexterp_agent/agent_runtime, docs/architecture/openclaw-progressive-manual-runtime.md`；测试 `tests/unit/agent_runtime, tests/unit/capability_service`
- **物料主数据与检索** (`item_master`)：代码 `src/nexterp_agent/item_master, data/material_master, tools/material_master_browser.html`；测试 `tests/unit/item_master`
- **ERPNext ToolCall 与 Adapter** (`erpnext`)：代码 `src/nexterp_agent/erpnext, frappe_apps/agent_bridge`；测试 `tests/unit/erpnext`
- **公司项目员工仓库供应商主数据** (`master_data`)：代码 `data/master_data, scripts/master_data`；测试 `tests/unit/master_data`
- **Capability API 与确定性编译** (`capability_service`)：代码 `src/nexterp_agent/capability_service, scripts/openclaw`；测试 `tests/unit/capability_service`
- **OpenClaw Plugin 与隔离运行时** (`openclaw`)：代码 `scripts/openclaw, frappe_apps/agent_bridge`；测试 `tests/unit/capability_service`

## 最近完成

- 物料批量高召回检索 v0.6 已提交， focused tests 9 passed。
- 物料录入草稿 v0.7 已提交，分析阶段不写 ERPNext。
- OpenClaw 工作台主链已接入材料申请、采购闭环和身份情境层。

## 下一步

1. 完成维护 CLI、文档审计和项目 Skill 的冷启动验收。
2. 归档已完成计划和旧 Runtime 对照文档，保留当前架构入口。
3. 继续用每个里程碑一个任务的方式开发，阶段结束更新 checkpoint 和 handoff。

## 验证命令

- `unit_item_master`: `python -m pytest tests/unit/item_master -q`
- `fast_regression`: `python -m pytest -q -m "not integration and not llm and not erpnext_write and not slow"`
- `full_python`: `python -m pytest -q`
- `project_resume`: `python scripts/dev/project_context.py resume`
- `project_check`: `python scripts/dev/project_context.py check`

## 维护边界

- Git 和测试结果是项目事实来源，聊天记录不是事实来源。
- 不提交 `.env`、`.secrets`、`data/runtime/` 日志、真实 ERPNext 凭据或业务运行数据。
- 阶段结束、提交前或交接时更新状态，不要求每次提交都改状态。
