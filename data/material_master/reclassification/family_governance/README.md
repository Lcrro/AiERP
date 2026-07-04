# 物料族规则人工治理工作区

本目录用于把“物料族候选词清单”转成可执行的物料族规则。

## 输入

候选词清单：

```text
data/material_master/reclassification/material_family_candidate_terms.tsv
```

当前新分类浏览数据：

```text
data/material_master/reclassification/material_master_browser_data_reclassified.json
```

参考说明：

```text
docs/reference/material-family-candidate-terms.md
docs/reference/material-category-taxonomy-v0.1.md
```

## 人工治理原则

1. 不按字符串机械合并，要按真实业务含义判断。
2. 物料族回答“这是一类什么东西”，材质、品牌、用途、尺寸、连接方式、强度等级等放到族内属性。
3. 同一个词如果横跨多个系统或用途，例如 `接头`、`弯头`、`三通`，必须拆分。
4. 不直接修改 `material_master.tsv`，不写 ERPNext。
5. 本阶段输出的是规则建议，不是最终导入结果。

## 输出文件

每个子代理只写自己的文件：

```text
family_rules_batch_01_pipe.tsv
family_rules_batch_02_fastener_lifting.tsv
family_rules_batch_03_tools.tsv
family_rules_batch_04_electrical_safety.tsv
family_rules_batch_05_misc.tsv
```

## 输出字段

TSV 字段固定如下：

```text
domain
candidate_term
decision
suggested_family
split_rule
family_attributes
include_examples
exclude_examples
priority
confidence
reason
```

字段说明：

| 字段 | 说明 |
|---|---|
| `domain` | 负责领域，例如 `管材管件阀门`、`紧固件与连接件` |
| `candidate_term` | 候选词，例如 `接头`、`钻头` |
| `decision` | `solidify`、`split`、`attribute_only`、`reject` 四选一 |
| `suggested_family` | 建议物料族；拆分时用 `；` 分隔多个族 |
| `split_rule` | 需要拆分时说明按什么拆，例如按系统/用途/材质/连接方式 |
| `family_attributes` | 族内属性字段，用 `；` 分隔 |
| `include_examples` | 应纳入该族的标准名称样例 |
| `exclude_examples` | 不应纳入该族的反例 |
| `priority` | `P0`、`P1`、`P2`，P0 表示优先固化 |
| `confidence` | `high`、`medium`、`low` |
| `reason` | 简短说明判断依据 |

## 决策口径

- `solidify`：候选词边界清楚，可以直接作为物料族规则。
- `split`：候选词有价值，但必须拆成多个物料族。
- `attribute_only`：候选词更像属性，不应作为物料族。
- `reject`：误命中或业务意义太弱，暂不治理。

## 合并结果

合并命令：

```powershell
python scripts\merge_family_rule_batches.py
```

合并输出：

```text
material_family_rules.tsv
material_family_rules_summary.json
```

当前合并状态：

```text
规则总数：204
solidify：104
split：73
attribute_only：27
P0：86
P1：85
P2：33
```

这些规则是后续扩展 `material_family` 浏览层、Resolver 和最终物料主数据治理规则的输入，不直接写 ERPNext。

## 当前接入状态

`scripts/build_material_master_browser_data.py` 已读取合并后的 `material_family_rules.tsv`：

- `solidify`：直接生成 `material_family`。
- `split`：写入 `family_split_candidates` 和复核说明；当拆分候选族明确出现在标准名称中时，保守归入该候选族。
- `attribute_only`：写入 `family_attribute_terms`，不改变物料族。

物料族归属以 `item_name` 为主，`aliases` 只用于搜索展示，不反向决定主物料族。
