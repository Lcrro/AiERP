# item-master-search-v0.1 Plan

## Summary

This milestone builds the first stable material master and material search layer
for Nexterp Agent.

Goal:

```text
员工用自然语言新增/查找物料
  -> 系统识别物料类别、规格、别名和候选
  -> 规则引擎补齐企业默认值并检查缺失信息
  -> ERPNext 创建或返回准确 Item
```

This milestone does not try to solve every industry taxonomy. It creates the
architecture, rules format, and first working examples so the company can extend
them safely.

## Why This Exists

ToolCall can already create an ERPNext `Item`, but raw document creation is not
enough for real material master data.

Real users may say:

```text
1.5 冷板
铁皮
SPCC 卷料
那个上次采购的薄料
```

The system must not blindly create duplicates or guess a unique material when
the wording is ambiguous.

The correct product behavior is:

```text
high confidence + complete specs
  -> create or select automatically

low confidence
  -> show candidates and ask for confirmation

missing required specs
  -> ask targeted follow-up questions

possible duplicate
  -> recommend existing Item before creating a new one
```

## References

- ERPNext Item Group: Item groups classify items and can carry group-level
  defaults.
- ERPNext Item Attribute and Item Variants: attributes and variants should be
  used when one item family has systematic variations such as size, color, or
  model.
- ERPNext Batch: batch numbers track groups of the same item through stock
  transactions when batch tracking is enabled.

## Architecture Target

```text
User text
  -> Agent extracts Item intent
  -> Material alias/search layer finds candidates
  -> Material rules engine validates category and specs
  -> Coding engine generates item_code when needed
  -> agent_bridge creates Item through ERPNext
  -> ToolResult returns created Item or clarification request
```

## Scope

Included:

- material group strategy
- required specification templates by group
- alias dictionary for common names and local names
- duplicate/candidate search
- item code generation
- ERPNext Item custom fields for common specs
- `agent_bridge.api.create_item_from_intent`
- local tests against ERPNext sandbox
- docs and operator runbook

Excluded for v0.1:

- complete industry-wide material taxonomy
- production approval workflow
- permission/policy agent
- advanced vector database deployment
- migration of existing company material master from spreadsheets

## Milestones

### A. Material Master Standard

- [x] Define first-level material group strategy.
- [x] Define second-level groups for common manufacturing examples.
- [x] Define rule for what belongs in Item Group versus specification fields.
- [x] Define batch/serial policy by material family.
- [x] Document examples:
  - raw metal sheet
  - raw plastic granule
  - electronic component
  - packaging material
  - finished good
  - service item

Acceptance:

- A user can understand where a new material should be classified.
- The document distinguishes category, specification, variant, and alias.

### B. Rule Configuration

- [x] Add `config/item_master_rules.yaml`.
- [x] Define group keys, labels, ERPNext item groups, code prefixes, defaults.
- [x] Define required specs per group.
- [x] Define default `has_batch_no`, `create_new_batch`, and `has_serial_no`.
- [x] Define aliases for first examples.

Example:

```yaml
groups:
  raw_metal_sheet:
    label: 原材料 / 金属材料 / 板材
    erpnext_item_group: 原材料
    code_prefix: RM-MET-SHT
    default_uom: Kg
    defaults:
      is_stock_item: 1
      is_purchase_item: 1
      is_sales_item: 0
      include_item_in_manufacturing: 1
      has_batch_no: 1
      create_new_batch: 1
    required_specs:
      - material
      - thickness
      - width
      - form
      - standard
```

Acceptance:

- Rules can be loaded without ERPNext.
- Invalid rule files fail with useful errors.

### C. ERPNext Item Custom Fields

- [x] Decide first custom fields:
  - `specification`
  - `material`
  - `drawing_no`
  - `standard`
  - `brand`
  - `model`
  - `package_spec`
  - `raw_name`
  - `alias_names`
- [x] Add setup method or script to create fields in local sandbox.
- [x] Document which fields are native ERPNext fields and which are custom.

Acceptance:

- Local sandbox Item form has the custom fields.
- Script is repeatable and does not duplicate fields.

### D. Rules Engine

- [x] Add `src/nexterp_agent/item_master/rules.py`.
- [x] Add intent data model.
- [x] Match group by explicit group key, alias, and keywords.
- [x] Validate required specs.
- [x] Generate clarification questions.
- [x] Produce normalized Item draft.

Acceptance:

- Complete input returns `status=ready`.
- Missing specs returns `status=needs_clarification`.
- Ambiguous group returns `status=needs_confirmation`.

### E. Coding Engine

- [x] Add `src/nexterp_agent/item_master/coding.py`.
- [x] Generate codes from rule prefix.
- [x] Check ERPNext for existing max sequence by prefix.
- [x] Avoid duplicate item codes.

Acceptance:

- `RM-MET-SHT-000001` style code can be generated.
- Repeated creation increments safely in local tests.

### F. Material Search Layer

- [x] Add `src/nexterp_agent/item_master/search.py`.
- [x] Search by exact item code.
- [x] Search by item name and alias.
- [x] Search by parsed specs.
- [x] Search enabled items by default.
- [x] Return candidates with score and match reason.

Acceptance:

- Query `1.5 冷板 SPCC` can return matching candidates.
- Query with exact item code returns one high-confidence candidate.
- Ambiguous query returns multiple candidates and requires confirmation.

### G. agent_bridge API

- [x] Add `agent_bridge.api.prepare_item_from_intent`.
- [x] Add `agent_bridge.api.create_item_from_intent`.
- [x] Validate Item Group and UOM exist before creation.
- [x] Write raw user name and normalized specs.
- [x] Return stable structure for Agent Runtime.

Acceptance:

- Agent can call one bridge method instead of raw `erpnext.create_document`.
- Bridge returns either created Item or clarification/candidate result.

### H. Tests

- [x] Unit tests for rule loading.
- [x] Unit tests for group matching.
- [x] Unit tests for missing specs.
- [x] Unit tests for code generation formatting.
- [x] Local integration test creates one material from intent.
- [x] Local integration test detects an existing similar material.

Acceptance:

- Unit tests pass without ERPNext credentials.
- Local integration tests pass with `NEXTERP_LOCAL_*`.

### I. Documentation

- [x] Add material master standard doc.
- [x] Add rules file reference.
- [x] Add local sandbox setup notes for custom Item fields.
- [x] Update project roadmap with this milestone.

Acceptance:

- Future work can resume from docs without relying on chat memory.

## First Example Scenario

Input:

```text
新增一个 1.5 冷板，SPCC，宽 1250，卷料，单位公斤
```

Expected normalized intent:

```json
{
  "raw_text": "新增一个 1.5 冷板，SPCC，宽 1250，卷料，单位公斤",
  "raw_name": "1.5 冷板",
  "item_name": "冷轧钢卷",
  "item_group_key": "raw_metal_sheet",
  "stock_uom": "Kg",
  "specs": {
    "material": "SPCC",
    "thickness": "1.5mm",
    "width": "1250mm",
    "form": "卷料"
  }
}
```

Expected rule result:

```json
{
  "status": "needs_clarification",
  "missing_specs": ["standard"],
  "questions": ["这个冷轧钢卷的执行标准是什么？"]
}
```

After user provides standard:

```json
{
  "status": "ready",
  "item_code": "RM-MET-SHT-000001",
  "item_doc": {
    "doctype": "Item",
    "item_code": "RM-MET-SHT-000001",
    "item_name": "冷轧钢卷",
    "item_group": "原材料",
    "stock_uom": "Kg",
    "is_stock_item": 1,
    "is_purchase_item": 1,
    "is_sales_item": 0,
    "include_item_in_manufacturing": 1,
    "has_batch_no": 1,
    "create_new_batch": 1
  }
}
```

## Design Principles

- Do not let the LLM invent item codes.
- Do not let the LLM decide required specs without rules.
- Keep raw user text for audit and later alias learning.
- Prefer existing Item reuse over duplicate creation.
- Ask short targeted questions when confidence is low.
- Use ERPNext native Item Group, Item Attribute, Variant, Batch, and UOM
  concepts where they fit.
- Use custom fields only for company-specific master data that ERPNext does not
  model directly.
