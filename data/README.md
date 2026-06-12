# 数据目录

数据目录按“数据生命周期”管理，避免原始采购清单、物料治理中间结果、ERPNext 导入报告和沙盘运行报告混在一起。

## 当前兼容目录

| 目录 | 状态 | 说明 |
|---|---|---|
| `material_purchase_2024/` | 兼容保留 | 当前物料采购清单、标准物料候选、治理结果和导入报告仍主要在这里，现有脚本和测试仍依赖该路径。 |
| `scenario/` | 兼容保留 | 当前土木公司沙盘 seed、runner、smoke 报告仍在这里。 |

## 目标目录

| 目录 | 用途 |
|---|---|
| `material_master/purchase_2024/raw/` | 原始输入，只读，不覆盖。 |
| `material_master/purchase_2024/working/` | 中间处理结果，可重复生成。 |
| `material_master/purchase_2024/curated/` | 已治理或可发布的标准物料候选。 |
| `material_master/purchase_2024/exports/` | 给 ERPNext 或其他系统导入的文件。 |
| `material_master/purchase_2024/reports/` | 校验报告、统计报告、导入报告。 |
| `material_master/purchase_2024/batches/` | 分批处理输入和输出。 |
| `scenarios/civil_company_day/` | 小型土木公司一日运转沙盘数据。 |
| `runtime/` | 未来 Agent Runtime 会话、日志和临时运行状态。 |

## 迁移规则

- 原始数据先复制后迁移，确认脚本路径更新后再清理旧位置。
- 中间结果必须能由脚本重建。
- `curated/` 里的文件才代表后续可用于建档、检索或导入的稳定候选。
- ERPNext 写入报告和 smoke 报告放 `reports/` 或 `smoke/`，不要混入标准物料本体。
- 不提交密钥、真实生产业务数据或临时运行日志。
