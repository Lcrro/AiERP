# 采购频次发现 v0.6：目录对齐与族级决策

状态：已生成本地审阅包，待业务确认；本轮不写入 ERPNext、不修改 Excel，也不自动生成 SKU。

## 目的

v0.5 已经把 1,273 条实际采购记录按物料族、规格、频次、单位和模糊相似候选拆开，但频次本身不能证明“可以合并”。本轮在不改变 v0.5 原始结果的前提下增加一层可审阅的决策：

- `selector`：同一标准类型内按有限 SKU 轴选择，其他字段仅作描述或采购条件；
- `configurable`：需要较完整配置才能确定可采购物料，缺字段时不得发布；
- `split_required`：当前族过于宽泛，必须先拆到现有标准类型；
- `single_spec_keep`：高频但尚未发现多规格，先保留单规格；
- `defer_multi_spec`：有多规格但频次不足，排在高频族之后；
- `defer`：非本轮优先族，保留证据、不建模板；
- `blocked`：存在服务、笼统、数量或特定物料阻断项。

## 重点族决策

本轮对 19 个高频多规格族给出明确的形态建议。`螺丝`、`膨胀螺丝`、`灭火器` 的建议是先拆分，不能直接建立一个大选择器；PPR 管件、接头等在各自族内建立有限选择轴；高压胶管、吊带、钢丝绳等采用配置型，并要求安全/结构字段补齐后再审阅。

每个族的 `review-decisions.jsonl` 还记录：

- 目录匹配状态及已有标准类型候选；
- SKU 选择属性、必填属性、描述属性、采购属性；
- 历史单位可靠性和“不得自动换算”标记；
- 同日重复行、去重事件和跨日期重复信号；
- v0.5 发布状态和本轮人工审阅门槛。

其中 `ready_for_template_review` 只表示证据齐全、可以优先做人工模板审阅，仍然不允许自动发布；`manual_review_required` 表示还存在属性、单位或 v0.5 质量缺口。

## 模糊候选安全边界

保留 v0.5 的完整模糊候选，但追加 `reconciliation_action`。结构标记、族决策或拆分要求存在差异时统一为 `do_not_merge`，例如普通弯头/内丝弯头、灭火器/灭火器箱、三通/异径三通等。即便同族候选也只进入人工别名审阅，绝不自动合并。

## 运行

```powershell
$env:PYTHONPATH = 'src'
python scripts/material_master/discover_procurement_frequency_v0_6.py
```

可用参数：`--source` 指定实际采购清单，`--output-root` 指定本地输出目录。默认输出到：

`.runtime/material-master/frequency-discovery-v0.6/`

主要文件：

- `discovery-summary.json`：数量、决策、覆盖率和只读声明；
- `review-decisions.jsonl`：每个物料族一行的 v0.6 决策；
- `clusters.jsonl`：v0.5 族记录加 `v6_decision`；
- `fuzzy-review-candidates.jsonl`：带禁止合并护栏的模糊候选；
- `quality-audit.json`：决策、单位、频次和模糊边界审计；
- `_v0.5/`：本次运行使用的 v0.5 暂存结果。

## 本轮验收重点

1. 先确认 `split_required` 族的拆分去向，再建立模板；
2. 对 `required_attribute_gaps` 非空的族补字段规则；
3. 处理单位可靠性为 `weak`/`missing` 的族，不能用历史单位静默替换；
4. 只从 `selector`/`configurable` 中挑选小范围试点，完成人工复核后再进入后续物料标准化；
5. 在 v0.6 通过业务审核前，不允许调用发布、ERPNext 写入或批量 SKU 生成。
