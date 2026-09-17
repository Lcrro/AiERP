# 团队交接与环境恢复

本页用于把 GitHub 仓库交给另一支开发团队。Git 是代码、测试、版本化规则和非敏感发布数据的来源；ERPNext 仍是权限、工作流、库存与正式单据的事实来源。

## Git 分支与审核

- 正式分支：`main`。
- 功能开发从 `main` 创建短期分支，通过 Pull Request 合并。
- `quality` CI 必须通过；涉及 ERPNext 写入的变更还必须附上测试账套的验收报告。
- CODEOWNERS 默认由 `@Lcrro` 审核。

## 新机器最短路径

```powershell
git clone https://github.com/Lcrro/AiERP.git
cd AiERP
powershell -ExecutionPolicy Bypass -File scripts\dev\team_handoff_bootstrap.ps1 -Action doctor `
  -V4Workbook "C:\secure-transfer\龙华项目公司标准物料示范清单_第四轮附件治理.xlsx"
```

确认 Docker Desktop 已启动后，用固定确认文本建立两个隔离测试账套：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev\team_handoff_bootstrap.ps1 -Action bootstrap `
  -V4Workbook "C:\secure-transfer\龙华项目公司标准物料示范清单_第四轮附件治理.xlsx" `
  -Confirm BOOTSTRAP-NEXTERP-TEST-SANDBOX
```

该命令只允许写入：

- `material-test.localhost`（端口 8003）；
- `material-classification-v4.localhost`（端口 8004）。

它会建立 Python 环境、同步本地目录数据库、导入 GPC 与 V4 主数据、创建最小业务主数据，并执行写后回读。凭据随机生成在 Git 忽略的 `.secrets/` 中，不会打印或提交。

启动门户：

```powershell
& .venv\Scripts\python.exe scripts\dev\agent_workbench.py --port 8788 --profile material_test
```

## 安全交接包

非敏感数据包可以这样生成：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev\export_team_handoff.ps1 `
  -V4Workbook "C:\Users\SGJ\Downloads\龙华项目公司标准物料示范清单_第四轮附件治理.xlsx" `
  -IncludeReferenceDatabase
```

输出位于 Git 忽略的 `outputs/team-handoff/`，包含 V4 原始工作簿、版本化物料发布数据、可选的参考目录数据库和逐文件 SHA-256。它明确不包含 `.env`、`.secrets`、ERPNext 数据库、运行日志或会话。

以下内容只能通过团队批准的密码管理器或加密通道传递：

- 实际启用的 `.env` 值；
- 两个测试 Site 的管理员凭据；
- 两套测试用户 API 凭据；
- DeepSeek/OpenClaw Token（仅在启用 AI 工作台时）。

推荐新团队优先用可重复脚本重建测试 Site，而不是传递数据库备份。确需传递备份时，必须在交付前加密，接收方校验 SHA-256，导入后立即轮换所有密码和 API Secret。

## 验收

仓库检查：

```powershell
python -m pytest -q -m "not integration and not llm and not erpnext_write and not slow"
python scripts\dev\project_context.py snapshot
python scripts\dev\project_context.py audit-docs
python scripts\dev\project_context.py check
```

两个物料账套回读：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev\team_handoff_bootstrap.ps1 -Action verify `
  -V4Workbook "C:\secure-transfer\龙华项目公司标准物料示范清单_第四轮附件治理.xlsx"
```

GPC 业务闭环：

```powershell
& .venv\Scripts\python.exe scripts\acceptance\material_business_portal_e2e.py all
```

验收报告位于 `.runtime/acceptance/material-business-portal/`，不提交 Git。报告必须证明预览确认、幂等、审批、双供应商报价、采购订单、部分收货、采购退货、剩余收货、项目领料/退料和库存回读全部通过。

## 禁止项

- 不向 GitHub 提交 `.env`、`.secrets`、数据库备份或真实业务文档。
- 不把测试身份切换器部署到生产模式。
- 不允许浏览器提交 Site URL、ERPNext 凭据或底层 ToolCall 参数。
- 不把模型或向量候选直接提升为已审核物料。
