# 物料主数据 SKU 草案 v0.3

本阶段把 `standard_material_candidates_curated.tsv` 的 2,355 条标准物料候选，整理成可建档前复核的 SKU 草案。

本阶段不写入 ERPNext，只生成可复现的数据表。

## 入口脚本

```powershell
python scripts\build_standard_item_master_draft.py
```

默认输入：

```text
data/material_purchase_2024/standard_material_candidates_curated.tsv
```

默认输出：

```text
data/material_purchase_2024/standard_item_master_draft.tsv
data/material_purchase_2024/material_dedupe_review_queue.tsv
data/material_purchase_2024/material_missing_spec_questions.tsv
data/material_purchase_2024/material_import_ready_items.tsv
data/material_purchase_2024/standard_item_master_draft_summary.json
```

## 输出说明

### standard_item_master_draft.tsv

SKU 草案总表。每行是一条候选 SKU。

生成规则：

- 按 `标准名称 + 必填规格 + 标准分组 + 标准单位` 自动合并完全重复候选。
- 自动生成 `draft_sku_id` 和 `draft_item_code`。
- `draft_item_code` 只是草案编码，用于沙盘和后续复核，不等于最终 ERPNext 正式编码。
- A/B/C/D 等级取合并候选中的最保守等级。

### material_dedupe_review_queue.tsv

去重和冲突复核队列。

包含三类问题：

- `exact_duplicate_auto_merged`：完全重复，已自动合并。
- `unit_conflict_review`：名称和规格相同但单位不同，需要人工确认。
- `alias_conflict_review`：同一别名指向多个 SKU，检索时不能直接唯一命中。

### material_missing_spec_questions.tsv

补规格问题清单。

主要用于让业务人员补齐 C/D 级物料的关键信息，也包含部分有明确疑问的 B 级物料。

示例：

```text
请补充“门锁”的锁体型号、开孔尺寸。
请补充“PPR管件”的材质、口径、压力等级、连接方式。
```

### material_import_ready_items.tsv

可导入候选清单。

规则：

- A 级：`ready_to_import`
- B 级：`confirm_then_import`
- C/D 级：不进入本表
- 存在单位冲突或别名冲突的 A/B 项，先进入复核队列，不直接进入导入清单

## 当前生成结果

```text
source_candidate_rows: 2355
draft_sku_count: 2328
auto_merged_duplicate_source_rows: 27
import_ready_count: 588
missing_question_count: 2168
dedupe_issue_rows: 170
```

等级分布：

```text
源候选：A 160 / B 538 / C 1657
SKU 草案：A 157 / B 531 / C 1640
```

可导入候选：

```text
ready_to_import: 128
confirm_then_import: 460
```

## 重要口径

- 一个规格原则上对应一个 SKU。
- 稳定用途限定不能丢失，例如“办公室门锁”标准名可以是“门锁”，但“用途：办公室门”必须进入规格。
- 缺关键规格时宁可进入 C 级补问队列，不强行导入。
- 同名同规格不同单位不能自动合并。
- 同一别名指向多个 SKU 时，检索层必须让用户补规格确认。
