# 物料重分类工作区

本目录用于把 `material_master.tsv` 中的同名物料组重新归入统一标准类目。

## 输入

- `item_name_groups_all.tsv`
  - 1242 个同名物料组的全量输入。
- `item_name_groups_batch_01.tsv` 至 `item_name_groups_batch_05.tsv`
  - 分给 5 个子代理的输入批次。
  - 批次数量分别为 249、249、248、248、248。

## 分类依据

- `docs/reference/material-category-taxonomy-v0.1.md`

核心原则：

```text
分类只描述物料本质，不描述是否耗材、谁使用、是否常买、是否需要询价。
```

例如：

- `劳保耗材/手套` 应归一为 `劳保防护/手套`
- `工具器具/涂装工具` 应按实物归入 `工具耗材/刷具` 或 `工具量具/...`
- `工程材料/PPR管件` 应归入 `管材管件阀门/...`

## 子代理输出

每个子代理只写自己的输出文件：

- `category_mapping_batch_01.tsv`
- `category_mapping_batch_02.tsv`
- `category_mapping_batch_03.tsv`
- `category_mapping_batch_04.tsv`
- `category_mapping_batch_05.tsv`

输出字段固定为：

```text
group_id
item_name
old_groups
sku_count
suggested_category
suggested_subcategory
needs_split
split_basis
confidence
reason
```

## 合并校验

等 5 个输出批次全部完成后运行：

```powershell
python scripts/merge_category_mapping_batches.py
```

脚本会检查：

- 是否覆盖全部 1242 个 `group_id`
- 是否存在重复 `group_id`
- 一级类目是否在标准类目表内
- `needs_split` 是否只使用 `yes/no`
- `confidence` 是否只使用 `high/medium/low`
- 需要拆分时是否填写 `split_basis`

校验通过后生成：

- `material_category_mapping.tsv`
- `material_category_mapping_summary.json`

本阶段不直接修改 `material_master.tsv`，也不写入 ERPNext。
