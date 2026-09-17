# 团队交接准备 v0.1

状态：已完成（2026-09-17）

## 完成项

- [x] 修正项目状态和交接文档的 HEAD 语义：文档记录“生成基线 HEAD”，提交后的真实版本始终以 Git 当前 HEAD 为准。
- [x] 增加 `main` 合并所需的 GitHub CI、CODEOWNERS 和 Pull Request 检查模板。
- [x] 增加 `scripts/dev/team_handoff_bootstrap.ps1`，支持依赖诊断、两个固定 ERPNext 测试 Site 的可重复初始化和全量回读。
- [x] 增加 `scripts/dev/export_team_handoff.ps1`，生成不含凭据的 V4 源文件、版本化发布数据、参考目录数据库及逐文件 SHA-256 交接包。
- [x] 在 `material-test.localhost` 跑通材料申请到项目领退料的完整采购闭环。

## 主数据回读

- GPC：259 项受管物料，缺失 0，字段不一致 0，冲突 0；
- ChatGPT V4：386 个物料族、917 个规格 SKU，缺失 0，字段不一致 0；
- 本轮没有向生产账套写入数据。

## 完整业务验收

- run_id：`E2E验收-20260917-143707-40c3db56`；
- 材料申请：`MAT-MR-2026-00014`；
- 采购订单：`PUR-ORD-2026-00008`；
- 部分收货：`MAT-PRE-2026-00007`；
- 采购退货：`MAT-PR-RET-2026-00003`；
- 剩余收货：`MAT-PRE-2026-00008`；
- 项目领料：`MAT-STE-2026-00005`；
- 项目退料：`MAT-STE-2026-00006`；
- 受控命令：26 次，全部通过重复 request_id 幂等检查；
- 结果：申请审批、RFQ、两份报价、比价来源、采购订单、部分/剩余收货、采购退货、Stock Ledger、领退料库存恢复和失败场景零写入全部通过。
- 自动化回归：721 passed、8 deselected；项目上下文与文档链接检查通过。

完整报告只保存在 Git 忽略的 `.runtime/acceptance/material-business-portal/`，避免把测试账套业务记录提交到 GitHub。

## 安全交接边界

已生成的非敏感交接包位于 Git 忽略的 `outputs/team-handoff/`。`.env`、`.secrets`、ERPNext 数据库、API Secret、运行日志和会话从不进入交接压缩包或 GitHub。实际凭据只能通过接收团队批准的密码管理器或端到端加密通道交付，并在接收后轮换。
