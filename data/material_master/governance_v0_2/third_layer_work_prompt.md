# 三级物料名称治理批处理提示词

生成日期：2026-07-03

请先阅读：

```text
docs/reference/material-third-layer-governance-v0.1.md
```

你的输入是一个 `third_layer_work_inputs/batch_XXX.tsv` 文件。你只处理该文件中的行，不读取全量物料表，不写 ERPNext，不修改正式主表。

输出 TSV 字段固定为：

```text
item_code
current_item_name
current_required_specs
current_uom
target_top_category
target_second_layer_family
target_third_layer_name
decision
confidence
assumed_specs
manual_judgment
next_action
```

要求：

- 输出行数必须等于输入行数。
- 每个输入 `item_code` 必须且只能输出一次。
- `target_third_layer_name` 只保留核心商品类型/形态/稳定功能。
- 材质、品牌、规格、尺寸、连接方式、表面处理、用途、压力、型号等放进 `assumed_specs` 或保留在规格里。
- 不属于当前物料族时，使用 `decision=移出`，并填写正确的目标二级物料族。
- 信息不足但暂可归类时，使用 `decision=复核`，`confidence=low/medium`，并在 `next_action` 写清楚采购前要确认什么。
