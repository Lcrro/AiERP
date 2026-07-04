# 物料脚本目录

这个目录保存物料主数据从原始采购清单到发布版物料表的处理脚本。

当前开发优先围绕发布版 v0.3，不建议新功能直接依赖早期草案脚本。

## 常用入口

| 任务 | 命令 |
|---|---|
| 重新生成发布版 v0.3 | `python scripts\material_master\build_material_master_release_v0_3.py` |
| 合并 DeepSeek SKU 治理重复项 | `python scripts\material_master\merge_sku_governance_duplicates.py` |
| 运行单批 DeepSeek SKU 治理 | `python scripts\material_master\run_deepseek_sku_governance_batch.py` |
| 生成四级物料浏览数据 | `python scripts\material_master\build_material_master_browser_data.py` |
| 生成三级治理工作包 | `python scripts\material_master\build_third_layer_work_batches.py` |
| 生成三级人工预览 | `python scripts\material_master\build_third_layer_mapping_preview.py` |
| 生成二级物料族人工预览 | `python scripts\material_master\build_manual_family_mapping_preview.py` |

## 生命周期分组

### 1. 原始采购清单处理

这些脚本把采购 Excel / review catalog / 原始文本处理成标准候选或中间表。

```text
process_purchase_list.py
export_review_catalog.ps1
merge_review_catalog.py
build_standard_material_input.py
split_standard_material_input_batches.py
merge_standard_material_candidate_batches.py
build_standard_item_master_draft.py
```

### 2. 早期物料主表与检索评估

这些脚本服务早期 `material_master.tsv` 和检索评估，保留用于兼容和对照。

```text
build_material_master.py
build_material_master_browser_data.py
run_material_search_eval.py
summarize_material_catalog_composition.py
import_review_catalog_to_postgres.py
resolve_material_conflicts.py
export_material_group_mapping.py
```

### 3. 一级类目与二级物料族治理

这些脚本处理类目重分类、物料族候选词和人工映射预览。

```text
apply_category_mapping.py
merge_category_mapping_batches.py
build_material_family_candidate_terms.py
merge_family_rule_batches.py
build_manual_family_mapping_preview.py
build_material_governance_v0_2.py
```

### 4. 三级名称治理

这些脚本把物料族下的同名物料整理成更合理的三级物料名称。

```text
build_third_layer_work_batches.py
build_third_layer_mapping_preview.py
build_screw_bolt_third_layer_preview.py
build_screw_governance_v0_2.py
build_screw_governed_preview.py
```

### 5. SKU 治理与发布版

这些脚本负责调用 DeepSeek 做 SKU 级治理、合并重复项，并生成当前发布版。

```text
deepseek_sku_governance_trial.py
run_deepseek_sku_governance_batch.py
merge_sku_governance_duplicates.py
build_material_master_release_v0_3.py
```

### 6. 专项样板

```text
build_glove_governance_sample.py
```

## 规则

- 新脚本优先写成可重复运行、可 dry-run 的命令。
- 新开发优先读取 `data/material_master/release_v0_3/`。
- 不要让 Agent Runtime 直接读取 `outputs/`。
- 不提交 `outputs/`，它是 DeepSeek 批处理和本地实验缓存。
- 如果某个脚本只服务历史过程，先在 README 中标明，不急着删除。
