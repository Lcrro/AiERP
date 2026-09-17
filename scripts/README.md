# 脚本目录

脚本按职责分区。根目录下保留少量兼容入口，例如：

```powershell
python scripts/smoke_erpnext.py --profile local --check auth
.\scripts\start_wsl_sandbox.ps1
```

实际脚本文件放在子目录中：

| 子目录 | 用途 |
|---|---|
| `dev/` | 本地开发、sandbox 启动、agent_bridge 同步、smoke 检查 |
| `erpnext/` | ERPNext 初始化、清理、导入、导入验证 |
| `material_master/` | 物料采购清单处理、标准物料候选、治理、检索评估 |
| `test_env/` | 跨平台 ERPNext 测试 Site 生命周期和 Windows 兼容脚本 |

跨平台新电脑诊断与初始化统一使用：

```bash
python scripts/dev/team_handoff_bootstrap.py doctor
python scripts/dev/team_handoff_bootstrap.py bootstrap --v4-workbook /secure/classification-v4-source.xlsx --confirm BOOTSTRAP-NEXTERP-TEST-SANDBOX
python scripts/dev/team_handoff_bootstrap.py verify --v4-workbook /secure/classification-v4-source.xlsx
```

两个物料测试 Site 的跨平台入口是 `scripts/test_env/material_sites.py`。既有 `.ps1` 文件保留用于 Windows 兼容，不再作为 Linux 交接入口。

物料脚本较多，具体分组见：

```text
scripts/material_master/README.md
```

常用物料主数据命令：

```powershell
python scripts/build_material_master.py
python scripts/build_glove_governance_sample.py
python scripts/build_material_master_browser_data.py
python scripts\material_master\build_material_master_release_v0_3.py
python scripts/build_material_family_candidate_terms.py
python scripts/merge_category_mapping_batches.py
python scripts/apply_category_mapping.py
python scripts/merge_family_rule_batches.py
```

## 规则

- 新脚本优先放入对应子目录。
- 根目录只保留兼容 wrapper 或非常明确的主入口。
- 可复用业务逻辑不要长期放在脚本里，应迁入 `src/nexterp_agent/...`。
- 写入 ERPNext 的脚本必须有 dry-run 或显式 `--apply` / `--execute` 开关。
