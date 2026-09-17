# 龙华实际采购清单物料族发现 v0.4

状态：第四轮审核意见落地，仍为只读分析，未写入 ERPNext。

## 本轮目标

v0.3 将族规则、历史单位和源数据异常放在同一个 `publish_gate` 中，导致“族模板已经可以审阅”和“历史行暂时不能发布”无法区分。v0.4 保留 v0.3 的族级解析与全部来源证据，拆成三个独立状态：

- `family_template_status`：族模板是否值得进入人工审阅；
- `source_data_quality`：历史单位、数量和服务/笼统标记是否可以支撑数量与价格处理；
- `publication_readiness`：是否可以进入受控发布审阅；仍不代表自动发布。

## 三轴口径

### 族模板成熟度

- `ready_for_review`：显式族且没有字段质量标记，可一次确认模板属性；
- `review_required`：显式族但字段缺失/歧义，或规则来源混合；
- `candidate`：词面族候选，必须先确认归类与别名；
- `blocked`：未解决或明确阻断。

该轴不再被历史单位冲突拖后。比如高压胶管即使历史单位混乱，也可以先审阅“长度、结构规格、公称尺寸”模板。

### 源数据质量

- `ready`：单位策略已定义、单位可信、数量可用；
- `ready_with_price_gap`：结构可用但部分历史行没有价格；
- `review_required`：单位策略缺失、单位冲突或需要校正；
- `blocked`：服务/物流、笼统采购、数量异常或明确特定物料。

未知族不再默认推荐“件”。此时 `uom_quality.policy_status=missing`、`status=policy_missing`，历史单位只作为证据，直到族模板确认后再定义采购/库存单位。

### 发布准备度

只有族模板和源数据两轴都通过，才会得到 `ready_for_review`；任何阻断项为 `blocked`，其余为 `review_required`。所有状态均不能绕过人工确认自动创建 SKU。

服务、维修、快递、运费、“一批”等标记现在真正进入 `blocked`，不再只是普通复核提示。

## 审核队列

`review-queues.json` 按投入产出比拆分队列：

1. `template_review_priority`：13 个高频多规格且已有显式/混合规则的族，先确认模板一次；
2. `lexical_high_repeat_review`：6 个高频多规格但仍是词面候选的族，先人工确认族归属；
3. `high_repeat_single_spec_review`：19 个高频单规格族，确认是否值得建立标准类型；
4. `deferred_low_repeat`：730 个低频或一次性族，暂缓逐项处理；
5. `blocked`：服务、笼统、数量异常或明确阻断项。

该顺序避免把 730 个低频族当作第一批人工任务。

## 模糊候选

模糊候选不再只导出前 500 对。所有候选完整写入 `fuzzy-review-candidates.jsonl`，同时标记：

- `structure_sensitive`：数字规格或弯头/接头、内丝/外丝、红/黑模板等结构词存在差异，优先复核；
- `semantic_near`：词面接近但没有检测到结构差异。

任一候选都只用于发现可能同族，固定为“人工复核，不自动合并”。

## 本轮全量结果

对 1273 行实际采购清单全量重跑：

- 807 个候选族，802 个有族假设，候选行覆盖率 99.61%；
- 族模板 `ready_for_review` 28 个，覆盖 11.15% 行；
- 27 个族进入真正 `blocked`，其中源数据阻断 21 个；
- 未定义单位策略的族 799 个，覆盖 1180 行；
- 高复频多规格 19 个，其中显式/混合规则 13 个、词面候选 6 个；
- 模糊候选完整 4902 对，其中结构敏感 4205 对；
- `writes_erpnext=false`。

候选覆盖率不等于正确率，词面候选仍需人工确认。价格只有在单位策略已定义且历史单位质量可信时才可用于比较。

## 运行

```powershell
python scripts/material_master/discover_procurement_frequency_v0_4.py
```

默认只读取 `实际采购清单`，只写 `.runtime/material-master/frequency-discovery-v0.4/`，不会修改 ERPNext 或源 Excel。

