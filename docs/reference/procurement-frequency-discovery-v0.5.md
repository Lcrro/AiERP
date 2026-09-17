# 龙华实际采购清单物料族发现 v0.5

状态：第五轮审核意见落地，仍为只读分析，未写入 ERPNext。

## 本轮修正

v0.4 仍有四个边界问题：属性解析标记和历史价格/数量标记混在一起；单位策略缺失被误算成源数据坏；低频多规格队列遗漏；完整模糊候选没有工作队列优先级。v0.5 在保留 v0.3/v0.4 解析器和原始证据的前提下修正这些问题。

## 状态定义

### 族模板状态 `family_template_status`

只看族识别和属性解析：

- `ready_for_review`：显式族且没有属性解析标记；
- `review_required`：显式族字段缺失/歧义，或规则来源混合；
- `candidate`：词面族候选，须先确认归类；
- `blocked`：未解决或明确阻断。

历史价格缺失、数量异常和单位冲突不会再降低族模板状态。例如高压胶管可以先审阅长度、结构规格和公称尺寸模板，再单独处理历史单位。

### 单位策略 `unit_policy_status`

- `defined`：族级采购/库存单位及允许来源单位已定义；
- `missing`：尚未定义，显示 `pending_unit_policy`，不默认推荐“件”。

PPR 管件和快速接头的常见采购单位按“件”建立了显式策略；防锈漆、通用管材等仍保留为待定义，避免未经确认地假设“件”或“桶”。

### 源证据质量 `source_evidence_quality`

- `ready`：单位策略已定义、历史单位可信且数量可用；
- `ready_with_price_gap`：结构和数量可用，但部分历史行没有价格；
- `pending_unit_policy`：族模板可分析，但单位策略尚未确定；
- `review_required`：单位已定义但历史单位冲突/缺失；
- `blocked`：服务/物流、笼统采购、数量异常或明确阻断项。

价格只有在单位策略已定义且历史单位可信时才可用于比较；无价格本身不阻断族模板复核。

### 发布准备度 `publication_readiness`

只有族模板、单位策略和源证据质量均满足要求才会得到 `ready_for_review`。该值仍然只是受控人工发布审阅，不代表自动创建 SKU 或写入 ERPNext。

## 互斥审核队列

`review-queues.json` 覆盖全部候选族，且每个族只出现一次，阻断项优先：

1. `blocked`：27 个；
2. `template_review_priority`：13 个高频多规格显式/混合族；
3. `lexical_high_repeat_review`：6 个高频多规格词面族；
4. `high_repeat_single_spec_review`：19 个高频单规格族；
5. `low_repeat_multi_spec_review`：38 个未被阻断的低频多规格族；
6. `deferred_low_repeat`：704 个低频或一次性族。

队列数量合计 807，与候选族总数一致。低频多规格不再遗漏，也不会和阻断队列重复。

## 字段级证据

`clusters.jsonl` 增加：

- `attribute_evidence`：属性值、来源行号和原始物料名；
- `attribute_field_confidence`：字段级可信度；
- `attribute_parse_flags`：只记录属性解析问题；
- `source_quality_flags`：只记录单位、数量、价格和服务类问题。

高压胶管的长度在明确 `m/米` 后标记高可信；层数、口径等混写数字仍保留原文并降低可信度，不据此自动生成 SKU。

## 模糊候选

所有 4902 对候选完整写入 `fuzzy-review-candidates.jsonl`，并增加工作队列：

- `priority_semantic_review`：涉及高价值族且没有结构冲突；
- `priority_do_not_merge`：涉及高价值族但规格/结构不同，优先标记禁止合并；
- `archive_low_priority`：只归档，不进入当前人工队列；
- `archive_do_not_merge`：低价值但存在结构差异，保留禁止合并证据。

任何模糊候选都固定为“人工复核，不自动合并”。

## 全量结果

输入文件 SHA-256：`85f24fad2b361e5e7025231c39fa8c1a3832dbbf692107d3d0f2c0778ab9adcf`。

对 1273 行实际采购清单重跑：

- 807 个候选族，802 个有族假设；
- 35 个族模板可进入审阅，覆盖 14.53% 行；
- 16 个族已有单位策略，791 个仍待定义；
- 27 个族阻断，其中源证据阻断 21 个；
- 19 个高频多规格族，13 个显式/混合规则、6 个词面候选；
- 模糊候选 4902 对，完整导出；
- `writes_erpnext=false`。

## 运行

```powershell
python scripts/material_master/discover_procurement_frequency_v0_5.py
```

默认只读取 `实际采购清单`，只写 `.runtime/material-master/frequency-discovery-v0.5/`，不会修改 ERPNext 或源 Excel。

