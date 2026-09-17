# 龙华实际采购清单物料族发现 v0.3

状态：第三轮只读质量门禁与族级解析，未写入 ERPNext。

## 为什么升级

第二轮已经能把 1,273 行压缩为可复核的候选族，但审计发现三个问题：高压胶管的长度被通用规格正则吞掉；PPR、灭火器和垫圈的字段语义需要按族解释；历史单位和价格不能直接作为 SKU 或频次决策依据。v0.3 保留第二轮全部原始证据，新增族级解析与质量门禁，不静默改写源表。

## 解析规则

- **高压胶管**：保留切割长度、结构规格和公称尺寸；例如 `36*2层-1寸-7.5m` 会产生 `结构规格=36*2层`、`公称尺寸=1寸`、`长度=7.5M`。不同长度会形成不同技术规格键。
- **PPR弯头**：把公称尺寸和角度分开；`110/45度` 记录为 `公称尺寸=110`、`角度=45°`。无“度/°”的斜杠仍标记为歧义，不自动判断是角度还是变径。
- **灭火器**：抽取 `灭火剂类型`（干粉、二氧化碳、泡沫、水基）和 `额定容量`（如 2KG、6L），防止同一“灭火器”族把介质和容量混成一个模糊规格。
- **平弹垫**：按已审计的语义规则归入“弹簧垫圈与平垫圈组合”；原“性能/等级”改名为“适配螺栓性能等级”，规格改为“适配螺纹”。来源规则保留，仍需人工确认。

## 单位门禁

历史 `单位` 永远保留为来源证据。程序只提供施工采购模板的推荐单位，不把推荐值回写到历史行：

- PPR管：米；PPR管件/阀门：件；
- 高压胶管：条（允许米、卷作为来源别名证据）；
- 灭火器：件；弹簧垫圈与平垫圈组合：套；
- 螺纹钢：吨；建筑用天然砂：吨；普通硅酸盐水泥：袋。

`uom_quality.status` 可能为 `trusted`、`normalized_alias`、`conflict` 或 `missing`。冲突/缺失会进入 `review_required`，不会进入规则就绪门禁。历史价格仅在数量和单位可信时标记为 `usable_for_comparison`，否则为 `observed_only`；没有价格本身不阻断模板复核。

## 频次口径

每个聚类同时输出：

- `line_count`：原始行数；
- `active_purchase_date_count`：发生过采购的日期数；
- `purchase_session_count`：日期+工序会话数；
- `distinct_event_count_approx`：日期+工序+技术规格键去重的近似事件数；
- `variant_count`：技术规格键数；
- `frequency_quadrant`：`high_repeat_multi_spec`、`high_repeat_single_spec`、`low_repeat_multi_spec` 或 `one_off_or_low_repeat`。

源表没有正式采购单号，所以这些指标不是实际订单数。工作台排序应显示多个指标，不应把任一指标称为“真实采购频次”。

## 发布门禁

`candidate_coverage_percent` 只表示有族假设；`rule_ready_for_review` 表示可进入人工规则审阅，不表示已批准、可创建 SKU 或可发布。v0.3 明确没有自动发布路径：

- 显式族、字段完整、单位符合模板口径：`rule_ready_for_review`；
- 词法候选、语义别名、单位冲突、规格歧义或数量异常：`review_required`；
- 阻断项、未解决项、服务/笼统项：`blocked`。

## 输出

默认输出到 `.runtime/material-master/frequency-discovery-v0.3/`（已忽略，不提交 Git）：

- `source-rows.jsonl`：逐行族级属性、技术规格键和质量标记；
- `clusters.jsonl`：聚类、频次四维指标、推荐单位、价格证据和复核原因；
- `fuzzy-review-candidates.jsonl`：语义阻塞发现的相似族对，决策固定为人工复核；
- `discovery-summary.json`：覆盖率、门禁、单位冲突和频次象限统计；
- `quality-audit.json`：高频多规格、高频单规格、低频多规格及单位冲突聚类索引。

运行：

```powershell
python scripts/material_master/discover_procurement_frequency_v0_3.py
```

本命令只读读取 `实际采购清单`，只写 `.runtime/`，`writes_erpnext` 始终为 `false`。
