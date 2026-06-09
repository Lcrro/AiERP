# Material Master Standard

This document defines the first material master standard for Nexterp Agent.
It is intentionally manufacturing-oriented and extensible, not an all-industry
taxonomy.

## Core Rule

Use ERPNext `Item Group` for business classification and defaults. Use
specification fields for properties that vary inside a family.

```text
Item Group
  -> decides default ERP behavior, code prefix, batch/serial policy, required specs

Specification fields
  -> describe the actual material clearly enough for purchasing, stock, BOM, and quality

Aliases
  -> preserve local names and rough user language without polluting standard names
```

Do not create an Item Group just because a size, color, brand, or thickness is
different. Those belong in specifications or variants.

## First Material Groups

| Group Key | Label | ERPNext Item Group | Code Prefix | Typical Use |
| --- | --- | --- | --- | --- |
| `raw_metal_sheet` | 原材料 / 金属材料 / 板材 | 原材料 | `RM-MET-SHT` | Steel sheet/coil/plate materials |
| `raw_plastic_granule` | 原材料 / 塑料橡胶 / 颗粒 | 原材料 | `RM-PLA-GRN` | Plastic and rubber granules |
| `electronic_component` | 原材料 / 电子元器件 | 原材料 | `RM-ELE-CMP` | ICs, resistors, capacitors, modules |
| `packaging_material` | 包装材料 | 包装材料 | `PKG` | Cartons, bags, labels, inserts |
| `consumable` | 辅料耗材 | 耗材 | `CNS` | Glue, oil, tapes, general consumables |
| `spare_part` | 备品备件 | 备品备件 | `SP` | Maintenance and equipment parts |
| `semi_finished_good` | 半成品 | 半成品 | `SF` | WIP and internal semi-finished goods |
| `finished_good` | 成品 | 产品展示 | `FG` | Sellable products |
| `service_item` | 服务 | 服务 | `SV` | Services without stock balance |

## Required Specifications

| Group Key | Required Specs |
| --- | --- |
| `raw_metal_sheet` | material, thickness, width, form, standard |
| `raw_plastic_granule` | material, grade, color, melt_index, package_spec |
| `electronic_component` | model, brand, package, key_parameter |
| `packaging_material` | material, size, package_spec |
| `consumable` | specification, brand |
| `spare_part` | model, brand, equipment |
| `semi_finished_good` | model, version, process_stage |
| `finished_good` | model, version, package_spec |
| `service_item` | service_scope, billing_unit |

These specs are v0.1 defaults. They should be adjusted after reviewing real
company material sheets.

## ERPNext Field Mapping

Native ERPNext fields:

```text
item_code
item_name
item_group
stock_uom
is_stock_item
is_purchase_item
is_sales_item
include_item_in_manufacturing
has_batch_no
create_new_batch
has_serial_no
description
disabled
```

Custom fields to add on `Item`:

```text
specification
material
drawing_no
standard
brand
model
package_spec
raw_name
alias_names
```

## Coding Rule

The LLM must not invent item codes. The backend generates codes from the rule
prefix:

```text
RM-MET-SHT-000001
RM-PLA-GRN-000001
RM-ELE-CMP-000001
PKG-000001
CNS-000001
SP-000001
SF-000001
FG-000001
SV-000001
```

## Batch And Serial Policy

| Policy | Meaning |
| --- | --- |
| `required` | Enable by default; used for traceability-sensitive materials |
| `optional` | Default off; allow user/company rule to enable |
| `none` | Do not enable unless an exception is explicitly approved |

Raw materials with quality or supplier-batch traceability normally use batch
tracking. Finished goods and spare parts may use serial tracking when individual
unit identity matters.

## Agent Behavior

The agent should:

```text
exact code match
  -> return the Item directly

complete new material intent
  -> prepare and create through agent_bridge

missing required specs
  -> ask targeted questions

ambiguous local name
  -> return candidates for confirmation

similar existing Item
  -> recommend reuse before creating a duplicate
```

The system should preserve `raw_name` and `alias_names` so local terms can be
learned without damaging the standard material name.
