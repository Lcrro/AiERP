# 物料检索质量测试集 v0.1

## 目标

`data/material_purchase_2024/material_search_eval_cases.csv` 收集 40 个来自 2024 采购 review、candidate、alias 数据的真实叫法，用来观察 `MaterialSearch(PostgresCatalogSearchClient(...))` 是否能召回正确候选，并且是否在泛称和高风险物料上保持确认/追问。

评估脚本：

```powershell
python scripts/run_material_search_eval.py
```

默认读取 `.env` 中的 `MATERIAL_CATALOG_DATABASE_URL`，输出总数、Top1 命中数、状态分布和失败案例。脚本默认返回 0，适合作为质量仪表盘；需要在 CI 中卡失败时使用 `--strict`。

## 用例覆盖

- 精确别名：`铜鼻子300A`、`镀锌内丝直接2寸`、`帆布手套`。
- 土名/错别字：`除绣灵`、`割咀`、`喷咀`、`丝芽`、`比塔`、`混泥土`、`兰色`。
- 泛称：`轴承`、`砂纸`、`接头`、`阀门`、`手套`。
- 高风险类：`吊带`、`卸扣`、`灭火器`、`安全绳`、`消防水带`。
- 规格类：`M16*70`、`DN50`、`3*16+1*10`、`Φ12`、`42.5水泥`。

## 判定规则

- `expected_status` 支持 `|` 分隔的允许集合，例如 `needs_confirmation|needs_clarification`。
- 若填写 `expected_top_item_name`，Top1 的 `item_name` 必须精确一致。
- 若填写 `expected_canonical_group`，Top1 返回的 canonical `item_group` 必须精确一致。
- `generic_guardrail` 和 `high_risk_guardrail` 额外要求状态不能是 `ready`。这类用例不要求都找不到，也不要求固定为某一个候选，重点是不要自动下结论。

## 当前结果

本轮在本地 PostgreSQL catalog 上运行脚本后记录：

- 总用例：40。
- 通过：16/40。
- Top1 名称命中：26/40。
- canonical group 命中：28/40。
- 状态分布：`ready` 20、`needs_confirmation` 12、`needs_clarification` 5、`not_found` 3。

典型失败：

- `铜鼻子300A` 被排到 `开口铜鼻子`，且 canonical group 与预期 `电气与自动化/电线电缆与敷设/电线电缆` 不一致。
- `镀锌内丝直接2寸`、`帆布手套` 能命中正确 Top1，但重复别名导致状态为 `needs_confirmation`。
- `一端丝芽一端焊接焊管`、`混泥土隔离剂2.7KG` 当前 `not_found`，因为标准化结果还停留在人工复核/候选数据。
- `轴承` 作为泛称被自动 `ready` 到 `轴承钢钢套`，说明泛称保护词表不足。
- `8T卸扣`、`2KG灭火器`、`安全绳Φ12` 等高风险品类缺少强制确认规则。

## 已知缺口

- 泛称保护词目前只覆盖 `接头` 等少量词，`轴承`、`砂纸`、`阀门`、`手套` 可能被高分别名直接打到 `ready`。
- 高风险物料没有独立风控层，`吊带5T*6m`、`8T卸扣`、`2KG灭火器`、`安全绳Φ12`、`防爆消防水带Φ80` 可能因为别名/规格命中而自动 `ready`。
- 错别字中有一部分只在 `manual_review_queue_from_review.csv` 或 `standard_material_candidates.csv`，未导入 `material_items/material_aliases`，例如 `除绣灵`、`丝芽`、`比塔`、`混泥土`、`兰色`，当前检索可能无法召回。
- `MaterialSearch` 只做包含匹配，没有拼写纠错、同音/形近词归一化、规格结构化解析和别名候选兜底。

## 下一步建议

- 扩展泛称词表：加入 `轴承`、`砂纸`、`阀门`、`手套`、`吊带`、`卸扣`、`灭火器`、`安全绳`、`消防水带`。
- 增加高风险 canonical group 保护：吊装索具、消防器材、高处防护命中时默认 `needs_confirmation`。
- 将人工复核队列中的已标准化错别字作为低置信 alias 导入检索索引，但保留 `needs_confirmation`。
- 增加规格解析：螺纹、口径、电缆芯数、直径、包装规格分别入结构化字段，减少纯文本包含带来的误排。
