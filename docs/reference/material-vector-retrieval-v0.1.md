# 物料向量召回基础层 v0.1

状态：向量通道已暂停用于生产检索、排序、归并和建单；仅保留显式离线影子评估。当前评估标签仍是银标/待复核，未达到向量维护门槛。

## 当前实现

`nexterp_agent.item_master.vector_retrieval` 提供一个不依赖外部模型的本地向量索引：

- 将中文字符二元/三元片段、英文/数字词片段哈希到固定维度向量；
- 向量经过 L2 归一化，以余弦相似度排序；
- 物料解析器把物料编码、名称、SKU 名称、已审核别名、规格、材质和型号组合为检索文档；
- GPC 参考目录的 Brick 候选也可在显式影子模式下计算同一套本地向量信号供审计；
- 向量结果只作为关键词/属性规则之外的影子信号；
- `ReleaseMaterialResolver` 和 GPC 参考目录的 `vector_mode` 默认是 `off`，只有离线评估显式传入 `shadow` 才建立索引和计算向量，避免门户请求承担未验证的 CPU 开销；
- 对已经有关键词/规格分数的候选，向量分数不加权、不参与排序；没有词法命中的向量候选只在离线评估中统计，暂不返回生产调用方；
- GPC Brick 候选同样只保留向量影子分数，不因向量命中新增或改排候选；
- 检索顺序固定为：数字编码精确匹配 → 已审核别名 → 标准类型中心词 → 规格/单位精确解析 → 词法候选 → 向量候选补充；
- 规格、结构、单位、启用状态和人工确认仍是最终门槛。自动选择只允许数字编码，或“已审核别名 + 所有必选属性完全一致”。

当前输出会保留 `vector_score` 和 `retrieval_sources`，便于审计候选是由哪条召回路径产生的。

## 边界

这不是语义 embedding 模型，也不是学习排序模型。它的优势是离线、稳定、可复现，适合先验证召回链路；字符相似度不能可靠理解同义词或业务语义，不能据此自动合并“看起来相似”的物料。

历史发布 TSV 与当前门户目录不是同一个数据面：历史包中的 1,979 行使用 `ADMIN-/SAFE-/FAST-` 等旧本地 ID；当前 GPC/ERPNext 发布面为 259 行，必须通过
`.runtime/material-master/gpc-material-placements.jsonl` 与
`.runtime/erpnext-material-test/material-item-code-map.json` 读取，并只接受纯数字 Item Code。`load_current_published_catalog()` 提供了这一受控读取边界，未映射或非数字记录会被排除。

频次发现的高置信聚类只用于排序和生成审核队列，不再直接写入 `aliases`，也不能让候选自动选择。只有
`data/material_master/approved_material_aliases_v0_1.jsonl` 中带有审核状态、目标物料和审核信息的记录，才会进入 `approved_aliases`。

## 来源身份与别名治理

采购行的身份不是一个裸行号，而是以下组合键：

```text
source_dataset + source_document + source_sheet + source_row
```

发布和频次发现还会在有原始行内容时保存 `source_row_hash`（稳定字段的 SHA-256）。相同的行号但不同数据集、文件或工作表永远不能关联；相同组合键但行内容哈希冲突也不能关联。旧运行时记录没有完整身份时只能迁移为实际采购清单的明确命名空间，不会再与历史参考表相连。

实验解析器产生的频次别名已经从当前发布读取路径移除。旧 `frequency_clusters_path` 参数仅为兼容保留并被忽略，避免历史高置信标签继续污染当前 SKU。

后续接入中文 embedding 时，应实现 `TextEmbeddingProvider`，并在离线评估集上与本地字符向量并行比较，不能直接替换最终规则。积累人工确认/拒绝样本后，才考虑 Cross-Encoder、逻辑回归或梯度提升学习排序。

## 验收

```powershell
python -m pytest tests/unit/item_master/test_vector_retrieval.py tests/unit/item_master/test_release_material_resolver.py tests/unit/item_master/test_high_recall.py -q
python scripts/material_master/evaluate_vector_shadow.py --catalog current
```

验收重点：

1. 相关规格候选可以被召回；
2. 精确编码仍然优先；
3. 泛化名称仍要求补充规格；
4. 未知物料不会因为向量分数被自动选中；
5. 发布后 SKU 变化会重建本地索引。
6. 影子评估的 `ranking_changed_count` 为 0（已有词法候选的顺序不被向量改变），且向量-only 候选不会改变生产候选集合；
7. 当前目录评估只出现数字 Item Code，不能回退到历史本地 ID；
8. `review_gate_status()` 在正样本少于 300 条或负样本少于 100 条时保持 blocked。

## 本轮审核结果（影子评估）

2026-08-31 使用 `scripts/material_master/evaluate_vector_shadow.py` 复测现有 40 条检索样例：

- 当前发布目录为 259 行，全部为纯数字 Item Code；与历史样例的标准名称覆盖率仅为 4/40（10%），说明评估标签仍混有旧目录术语，不能据此训练或启用排序模型；
- 影子模式的 `ranking_changed_count=0`，已存在词法/规格候选的顺序没有被向量改写；
- 旧历史发布包（1,979 行）中有 29/40 条出现向量信号，但本次测量中位延迟由约 331 ms 增至约 463 ms；这条路径目前只用于离线观察，不应直接作为门户默认排序；
- 当前目录样例中暂未出现可用的向量补充候选，下一步应先把 1,273 条实际采购记录的别名、规格变体和数字 Item Code 建立人工确认金标准，再决定是否引入语义 embedding 或学习排序。

## 第二轮（当前目录链接金标准）

本轮使用 `--linked-current` 将频次发现的 1,273 条原始名称与当前发布目录按完整来源身份、标准类型和规格做保守链接；无法唯一对应的记录不进入准确率分母。结果为 49 条银标链接样本，不能称为金标准。此前仅靠裸行号产生的 2 条跨来源碰撞已被剔除，其余记录仍留在待复核队列：

- 词法 Top-1 为 22/49（44.90%），Recall@5 为 28/49（57.14%）；影子向量未改变两项指标；
- `ranking_changed_count=0`，向量-only 候选仍未进入生产候选集；
- 2/49 条出现向量信号；词法中位延迟约 48.94 ms，显式影子模式约 64.22 ms；
- 生产 resolver 默认 `vector_mode=off`，因此不会为每个门户查询重复付出这段影子计算；
- 批量高召回路径在接收判定结果后仍重复执行严格自动选择门禁；严格目录中的非数字编码、未审核别名或缺少必选属性的候选只能进入人工补充/复核队列；
- 当前 300 条正样本候选和 100 条困难负样本候选全部为 `pending_review`，确认计数为 0/0；因此向量维护门槛为 blocked，不能开启向量排序或自动选料；
- 这一轮暴露的主要缺口是原始名称与标准类型/规格的确定性规范化仍不足（例如品牌前缀、口径写法和“弯头/接头”等宽窄类型），49 条银标样本不能替代人工金标准。

复测命令：

```powershell
python scripts/material_master/evaluate_vector_shadow.py --catalog current --linked-current
```

## 人工审核队列与向量门槛

审核候选由以下只读命令生成，命令不写 ERPNext，也不批准别名：

```powershell
python scripts/material_master/build_retrieval_review_set.py
```

输出为 `data/material_master/retrieval_review_v0_1.jsonl`（300 条正样本候选、100 条困难负样本候选）及对应 summary。审核人必须逐条填写 `review_decision`、`reviewer` 和 `reviewed_at`；只有审核通过的正样本才可迁移到 `approved_material_aliases_v0_1.jsonl`。

审核完成后使用以下显式晋级命令生成别名投影。命令会跳过 pending、负样本、缺审核人/时间戳和目标非数字的记录；同一别名指向多个目标时整组拒绝，并且仍不写 ERPNext：

```powershell
python scripts/material_master/promote_reviewed_aliases.py
```

本轮已增加模型辅助预审命令。它只生成独立的建议投影，保留原队列的
`review_decision` 为空，不填充人工审核人，不晋级别名，也不写 ERPNext：

```powershell
python scripts/material_master/model_pre_review_retrieval_queue.py
```

结果写入 `retrieval_review_v0_1.model_pre_review.jsonl`。每行包含
`likely_match`、`likely_non_match` 或 `needs_human`、置信度、理由、证据和
`source_audit_status`。模型建议只能帮助人工排序审核工作，不能满足
`review_gate_status()` 的 300/100 金标准门槛；尤其是缺少
`source_row_hash` 的银标记录必须先补齐来源证据再确认。

2026-09-01 已重新从原始 Excel 生成频次结果，31 条银标候选均补齐完整
来源身份和 `source_row_hash`。19 条高风险记录的模型辅助逐条复核使用：

```powershell
python scripts/material_master/resolve_assisted_retrieval_review.py
```

输出 `retrieval_review_v0_1.assisted_resolution.jsonl`：10 条合成错别字只确认
评测正例关系，明确禁止晋级生产别名；9 条真实采购简称根据既有治理记录
接受为候选召回关系，但缺少具体规格时仍不得自动选料。该结果不填充真人
审核字段、不写 ERPNext、不晋级别名，也不改变向量门槛。

向量通道只有在审核样本满足以下条件后才允许重新评估是否维护：正样本不少于 300 条、困难负样本不少于 100 条、Recall@5 ≥ 95%、Top1 ≥ 85%、困难负样本误匹配率 < 1%、相比词法 Recall@5 至少提升 5 个百分点且 Top1 不下降。评估器会输出 `vector_maintenance_gate.status=blocked` 或 `eligible_for_metric_check`；在此之前向量只能作为候选提示。
