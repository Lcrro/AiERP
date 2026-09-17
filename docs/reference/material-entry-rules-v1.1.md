# 物料分类与录入规则 v1.1

本规则用于从 `material_master_release_v1_0` 重新生成 `material_master_release_v1_1`。v1.1 是一份独立候选发布，不覆盖 v1.0，也不直接写入 ERPNext。

## 1. 四层结构

每一条 SKU 必须落在以下四层中：

1. `top_group`：业务大类，只表达业务域；
2. `material_family`：物料族，不表达品牌、项目、尺寸或包装；
3. `standard_name`：标准物料名称，只表达“是什么”；
4. SKU：标准名称加上会影响采购、库存或互换性的属性。

`item_group` 由大类和业务子组组成。尺寸、颜色、品牌、厚度、包装、强度、型号等全部作为属性，不新建为分类。

## 2. 名称和属性

- 显式的强度等级、尺寸、口径、包装词从标准名称移入 SKU 属性；原始名称进入 `source_item_name` 和 `aliases`，确保可追溯。
- 来源字段 `required_specs`、`brand`、`model` 是事实证据。规则引擎只归一化键名，不推断缺失值。
- 每个标准类型的 `required_attribute_keys` 取该类型来源 SKU 的属性并集（排除用途、套件组成等非身份描述字段）。同类型某 SKU 缺少并集中的字段时，写入 `missing_required_specs`，不得用默认值伪造。
- `stock_uom`、`purchase_uom`、`conversion_factor` 只在来源为空时分别使用安全结构默认值 `个`、库存单位和 `1`；这类默认不代表业务事实，仍保留来源字段。

## 3. 质量与使用策略

| 条件 | `quality_level` | `classification_status` | `agent_use_policy` |
| --- | --- | --- | --- |
| 字段齐全且无风险标记 | `standard` | `ready` | `auto_select_allowed` |
| 缺少类型必填属性 | `needs_review` | `needs_input` | `clarify_specs_before_use` |
| 候选分类、别名冲突或安全/压力/化学相关 | `needs_review` | `needs_review` | `confirm_before_use` |

安全消防、吊装索具、劳保防护、化工胶粘涂料、焊接切割、液压气动，以及名称中涉及压力、吊带、安全带、灭火、防毒、化学的物料，必须人工确认后才能使用。

## 4. 发布与审计

重建脚本是确定性的标准库程序：

```powershell
python scripts/material_master/rebuild_material_master_v1_1.py
```

输出目录 `data/material_master/release_v1_1/` 包含：

- `material_master_release_v1_1.tsv`：1979 条 SKU 新表；
- `material_type_dictionary.tsv`：标准类型字典；
- `material_attribute_templates.tsv`：类型属性模板；
- `sku_type_mapping.tsv`：SKU 到类型的可追溯映射；
- `audit_report.tsv/json`：缺失属性、候选分类、别名冲突和高风险确认项；
- `material_master_release_v1_1_summary.json`：行数、覆盖率、质量和策略计数。

只有 `classification_status=ready` 的记录才可被自动选择；本候选发布尚未切换为运行时权威目录，需完成审计与业务确认后再发布。
