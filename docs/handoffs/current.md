# 当前开发交接

新任务先运行 `python scripts/dev/project_context.py resume`，再按本次请求选择模块。

- 分支：`codex/project-maintenance-skill-v0.1`
- HEAD：`c950723f172c9c9c724a4272673d0cf5b40ff240`
- 工作区业务变化：`2` 个；运行时文件不纳入上下文。
- 当前里程碑：`project-maintenance-skill-v0.1`

## 入口

- workbench: `http://127.0.0.1:8788/`
- material_intake_lab: `http://127.0.0.1:8788/material-intake-lab`
- material_item_lab: `http://127.0.0.1:8788/material-item-lab`
- capability_api: `http://127.0.0.1:8790`
- erpnext_civil: `http://localhost:8002`

## 需要知道的事实

- 物料批量高召回检索 v0.6 已提交， focused tests 9 passed。
- 物料录入草稿 v0.7 已提交，分析阶段不写 ERPNext。
- OpenClaw 工作台主链已接入材料申请、采购闭环和身份情境层。
- 项目维护 CLI、文档审计、状态快照和交接文档已完成并通过 `check`。
- 历史计划、旧 Runtime 对照实验和旧机器说明已归档；项目 Skill 已安装并通过校验。

## 下一步

- 新 Codex 任务先运行 `resume`，再只读取本次涉及模块的代码、测试和文档。
- 下一业务里程碑完成后运行快速回归、`check`、`checkpoint --write` 和 `handoff --write`。
- 只有在里程碑边界显式运行长时 LLM/ERPNext 验收，不把外部测试放进日常循环。

## 开发规约

- 先核对 Git 工作区，保留用户未提交改动。
- 只读取本次相关模块的代码、测试和文档；不要遍历全部文档。
- 优先使用 CodeGraph，不可用时使用 `rg` 和 `.runtime/context/repo-map.json`。
- 写操作必须使用员工本人身份、明确确认、幂等 request_id 和执行后回读。
- 不读取或打包 `.env`、`.secrets`、凭据和运行日志。
