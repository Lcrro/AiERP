# 脚本目录

脚本按职责分区。根目录下保留同名兼容入口，因此旧命令仍可使用，例如：

```powershell
python scripts/smoke_erpnext.py --profile local --check auth
python scripts/run_civil_company_day_scenario.py --profile civil
python scripts/wizard_workbench.py --profile civil --port 8787
.\scripts\start_wsl_sandbox.ps1
```

实际脚本文件放在子目录中：

| 子目录 | 用途 |
|---|---|
| `dev/` | 本地开发、sandbox 启动、agent_bridge 同步、smoke 检查 |
| `erpnext/` | ERPNext 初始化、清理、导入、导入验证 |
| `material_master/` | 物料采购清单处理、标准物料候选、治理、检索评估 |
| `scenarios/` | 业务沙盘 seed、runner、ToolCall 覆盖校验 |

## 规则

- 新脚本优先放入对应子目录。
- 根目录只保留兼容 wrapper 或非常明确的主入口。
- 可复用业务逻辑不要长期放在脚本里，应迁入 `src/nexterp_agent/...`。
- 写入 ERPNext 的脚本必须有 dry-run 或显式 `--apply` / `--execute` 开关。
