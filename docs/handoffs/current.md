# 当前开发交接

新任务先运行 `python scripts/dev/project_context.py resume`，再按本次请求选择模块。

- 分支：`codex/project-maintenance-skill-v0.1`
- HEAD：`73d385e69069651908b253f69271b5b6fc273efe`
- 工作区业务变化：`54` 个；运行时文件不纳入上下文。
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

## 下一步

- 完成维护 CLI、文档审计和项目 Skill 的冷启动验收。
- 归档已完成计划和旧 Runtime 对照文档，保留当前架构入口。
- 继续用每个里程碑一个任务的方式开发，阶段结束更新 checkpoint 和 handoff。

## 开发规约

- 先核对 Git 工作区，保留用户未提交改动。
- 只读取本次相关模块的代码、测试和文档；不要遍历全部文档。
- 优先使用 CodeGraph，不可用时使用 `rg` 和 `.runtime/context/repo-map.json`。
- 写操作必须使用员工本人身份、明确确认、幂等 request_id 和执行后回读。
- 不读取或打包 `.env`、`.secrets`、凭据和运行日志。
