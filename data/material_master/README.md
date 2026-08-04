# 物料主数据

这个目录保存物料主数据的来源、治理中间表、浏览数据和发布版。

当前业务开发优先使用发布版 v0.3：

```text
data/material_master/release_v0_3/material_master_release_v0_3.tsv
```

它是给采购员浏览、给 Agent Resolver 检索、后续导入 ERPNext sandbox 的当前入口。

## 目录分层

| 路径 | 定位 | 是否作为当前入口 |
|---|---|---|
| `release_v0_3/` | 当前发布版物料表、浏览器数据和摘要 | 是 |
| `governance_v0_2/` | 二级族、三级名称、螺丝等人工治理工作区 | 否 |
| `reclassification/` | 旧物料名按新类目重分类的工作区 | 否 |
| `governance/` | 手套等早期专项治理样板 | 否 |
| `purchase_2024/` | 采购清单导入后的物料处理过程数据 | 否 |
| 根目录 `material_master.tsv` | 早期标准主表，保留用于对照和旧脚本兼容 | 否 |

使用原则：

- 新开发优先读取 `release_v0_3/material_master_release_v0_3.tsv`。
- 过程文件不直接作为 Agent Resolver 或 ERPNext 导入入口。
- 历史预览和专项治理文件保留可追溯性，不在本轮整理中搬家，避免破坏旧脚本路径。
- `outputs/` 是本地批处理缓存，已加入 `.gitignore`，不提交。

## 早期主表

```text
material_master.tsv
```

早期主表由 SKU 草案生成，目前主要用于对照和旧脚本兼容：

```text
data/material_purchase_2024/standard_item_master_draft.tsv
```

生成命令：

```powershell
python scripts\build_material_master.py
python scripts\build_material_master_browser_data.py
```

## 字段口径

| 字段 | 说明 |
|---|---|
| `item_code` | 唯一物料编码，稳定不变。 |
| `item_name` | 标准名称，不塞规格。 |
| `required_specs` | 影响 SKU 的关键规格。 |
| `optional_specs` | 辅助判断信息。 |
| `item_group` | 标准分组。 |
| `stock_uom` | 库存单位。 |
| `purchase_uom` | 常用采购单位，当前第一版先留空。 |
| `conversion_factor` | 采购单位到库存单位换算，当前第一版先留空。 |
| `aliases` | 别名、土名、历史叫法。 |
| `search_keywords` | 给员工搜索和 Agent Resolver 使用的检索文本。 |
| `brand` | 从规格中可确定的品牌。 |
| `model` | 从规格中可确定的型号。 |
| `status` | 主数据状态：`active`、`candidate`、`disabled`。 |
| `quality_level` | 数据质量：`standard`、`usable`、`needs_review`、`blocked`。 |
| `agent_use_policy` | Agent 使用策略：自动选择、确认后使用、补规格后使用或禁用。 |
| `source_refs` | 来源行和草案 ID。 |
| `governance_note` | 内部治理备注，不建议展示给普通员工。 |
| `updated_at` | 生成或最近治理日期。 |

## 早期主表使用原则

- 旧脚本和历史对照可以读取这张主表。
- 新的 ERPNext 导入、物料检索和 Agent Resolver 应优先读取发布版 v0.3。
- 采购清单、治理队列、批处理结果都视为过程文件，不作为最终主数据入口。
- 缺失规格和合并依据保留在 `governance_note`，不要塞进 ERPNext 普通描述字段。

## 发布版 v0.3

当前更适合给采购员浏览、给 Agent Resolver 检索、后续导入 ERPNext sandbox 的发布候选表是：

```text
data/material_master/release_v0_3/material_master_release_v0_3.tsv
data/material_master/release_v0_3/material_master_release_v0_3_browser_data.json
data/material_master/release_v0_3/material_master_release_v0_3_summary.json
```

生成命令：

```powershell
python scripts\material_master\build_material_master_release_v0_3.py
```

发布版构建默认输入：

```text
data/material_master/release_v0_3/sku_governance_unique_all.tsv
```

这个文件来自 DeepSeek SKU 治理批处理结果，已复制进发布目录作为可复现输入。原始 `outputs/` 目录只保留本地缓存，不作为项目依赖。

发布版字段口径：

| 字段 | 说明 |
|---|---|
| `item_code` | 发布 SKU 的稳定编码，沿用合并组的 canonical 旧编码。 |
| `item_name` | 第三层物料名称，用于四级浏览中的“物料名称”。 |
| `sku_name` | 采购员可读的 SKU 名称，例如 `帆布手套 加厚双层`、`漏电保护器 2P 32A`。 |
| `required_specs` | 最小采购规格，只保留会影响采购选择的关键字段。 |
| `top_group` | 一级类目。 |
| `material_family` | 二级物料族。 |
| `item_group` | ERPNext 可用的分组路径，当前为 `top_group/material_family`。 |
| `stock_uom` | 标准库存单位。 |
| `aliases` | 土名、历史叫法和可检索别名。 |
| `source_item_codes` | 被合并进该发布 SKU 的旧物料编码。 |
| `merged_count` | 合并来源数量。 |

当前校验结果：

```text
发布 SKU：1,984
覆盖源 SKU：2,328 / 2,328
一级类目：20
物料族：144
派生 SKU：21
重复 SKU 名称+规格键：0
空关键规格：0
```

## 专项治理样板

按完整物料族调用 DeepSeek 的治理试验：

```powershell
python scripts\material_master\deepseek_family_governance.py `
  --top-group 工具耗材 `
  --material-family 钻头
```

该流程会把同一物料族的全部 SKU 作为横向比较上下文，分批输出需要整理的编码，生成：

```text
data/material_master/governance_v0_4/工具耗材_钻头/family_governed.tsv
data/material_master/governance_v0_4/工具耗材_钻头/before_after.tsv
data/material_master/governance_v0_4/工具耗材_钻头/independent_review.tsv
data/material_master/governance_v0_4/工具耗材_钻头/independent_review.json
data/material_master/governance_v0_4/工具耗材_钻头/material_master_family_governed_preview.tsv
data/material_master/governance_v0_4/工具耗材_钻头/material_master_family_governed_browser_data.json
data/material_master/governance_v0_4/工具耗材_钻头/summary.json
```

流程固定为“整族生成 -> 硬校验 -> 独立语义复核 -> 人工确认 -> 发布”。独立复核只标记问题，不直接修改模型输出。对应问题会同时写入预览表的 `governance_note`，便于在网页中逐项查看。

这组文件仅为治理预览，不覆盖正式 `release_v1_0`。确认后再通过发布流程合入正式物料表。需要只重跑程序校验和输出生成时，可使用 `--reuse-responses --reuse-review`，不会再次调用 DeepSeek。

手套类物料专项治理样板：

```powershell
python scripts\build_glove_governance_sample.py
```

输出：

```text
data/material_master/governance/glove_governance.tsv
data/material_master/governance/glove_material_master_sample.tsv
data/material_master/governance/glove_governance_summary.json
```

`glove_governance.tsv` 记录每条旧物料保留、合并或修正到哪条标准 SKU；`glove_material_master_sample.tsv` 是治理后的手套类标准物料样板。

## 重分类工作区

同名物料组重分类结果放在：

```text
data/material_master/reclassification/
```

分类依据：

```text
docs/reference/material-category-taxonomy-v0.1.md
```

合并校验命令：

```powershell
python scripts\merge_category_mapping_batches.py
python scripts\apply_category_mapping.py
python scripts\build_material_master_browser_data.py --input data\material_master\reclassification\material_master_reclassified.tsv --output data\material_master\reclassification\material_master_browser_data_reclassified.json
```

当前输出：

```text
data/material_master/reclassification/material_category_mapping.tsv
data/material_master/reclassification/material_category_mapping_summary.json
data/material_master/reclassification/material_master_reclassified.tsv
data/material_master/reclassification/material_master_reclassified_summary.json
data/material_master/reclassification/material_master_browser_data_reclassified.json
```

本阶段不直接改 `material_master.tsv`。`material_master_reclassified.tsv` 是基于分类映射生成的新分类视图，便于和旧分类对照。

## 本地浏览页

生成浏览页数据：

```powershell
python scripts\build_material_master_browser_data.py
```

启动本地静态服务后访问：

```text
tools/material_master_browser.html
```

浏览页支持 `发布版 v0.3 / 螺丝三级预览 / 二级族人工预览 / 螺丝治理预览 / 新分类 / 旧分类` 切换。默认展示发布版 v0.3。普通物料视图按 `类目 -> 物料族 -> 物料名称 -> SKU 明细` 四级查看。
浏览页也支持 `物料视图 / 规则审查` 切换。规则审查用于查看某条物料族规则实际命中了哪些 SKU、哪些物料族和哪些分类。

螺丝三级预览读取二级族人工预览后，只处理 `紧固件与连接件 -> 螺丝/螺栓` 下的 SKU，把第三层物料名称拆成内六角螺丝、自攻螺丝、钻尾螺丝、普通螺栓、鱼尾螺栓、管片螺栓等。裸奔数据会使用合理近似值补全材质、强度等级和表面处理，但保留低置信度和采购前确认提示。

```text
data/material_master/governance_v0_2/manual_third_layer_mapping/screw_bolt_third_layer_mapping_v0_1.tsv
data/material_master/governance_v0_2/manual_third_layer_mapping/material_master_screw_bolt_third_layer_preview.json
```

重新生成命令：

```powershell
python scripts\material_master\build_screw_bolt_third_layer_preview.py
```

二级族人工预览读取人工映射表，不使用自动关键词规则覆盖正式主表：

```text
data/material_master/governance_v0_2/manual_family_mapping/pipe_valve_family_mapping_batch_001.tsv
data/material_master/governance_v0_2/manual_family_mapping/material_master_manual_family_preview.json
```

重新生成命令：

```powershell
python scripts\material_master\build_manual_family_mapping_preview.py
```

螺丝治理预览不覆盖正式主表，只把 `data/material_master/governance_v0_2/screw/screw_governance_candidates.tsv` 中的治理建议应用到一份预览表：

```text
data/material_master/governance_v0_2/screw/material_master_screw_governed_preview.tsv
data/material_master/governance_v0_2/screw/material_master_screw_governed_preview.json
```

重新生成命令：

```powershell
python scripts\material_master\build_screw_governed_preview.py
python scripts\material_master\build_material_master_browser_data.py --input data\material_master\governance_v0_2\screw\material_master_screw_governed_preview.tsv --output data\material_master\governance_v0_2\screw\material_master_screw_governed_preview.json
```

浏览数据会额外生成 `material_family` 字段，用于把同类物料聚合成“物料族”。例如钻头专项样板中：

- `冲击钻头`、`合金钻头`、`钨钢钻头`、`五坑钻头` 归入物料族 `钻头`
- `宝塔钻头开孔器` 归入物料族 `开孔器`
- `铣刀钻头` 暂独立为物料族 `铣刀钻头`，后续复核是否并入铣刀类耗材

当前浏览层还包含以下物料族样板：

- 紧固件：`内六角螺丝`、`六角螺丝`、`鱼尾螺丝` 等归入 `螺丝`；`膨胀螺丝`、`爆炸螺丝`、`膨胀钩` 归入 `膨胀锚栓`
- 手套：`帆布手套`、`乳胶手套`、`焊工手套`、`浸胶手套` 等归入 `手套`
- 管件：`PPR弯头`、`PVC弯头`、`焊接弯头` 等归入 `弯头`；`PPR三通`、`镀锌三通` 等归入 `三通`
- 门窗五金：`办公室门锁`、`防盗门锁`、`断桥铝门锁` 归入 `门锁`；`不锈钢挂锁`、`铜挂锁` 归入 `挂锁`

物料族规则表：

```text
data/material_master/reclassification/family_governance/material_family_rules.tsv
```

浏览数据生成脚本会读取这张规则表。`solidify` 规则用于生成物料族，`split` 规则用于展示拆分候选和复核提示；如果拆分候选族明确出现在标准名称里，脚本会保守归入该候选族，例如 `502胶水 -> 胶水`。`attribute_only` 规则用于提示族内属性词。这些规则目前只用于浏览和治理判断，不直接写回 ERPNext。

## DeepSeek 完整物料族治理 v0.4

完整物料族治理以正式发布表为只读输入，按物料族隔离生成规则、治理建议和独立复核结果。第一批包含：

```text
液压气动 / 胶管总成
管材管件阀门 / 弯头
管材管件阀门 / 三通
```

治理优先队列、批次清单、全量预览和待人工确认问题分别位于：

```text
data/material_master/governance_v0_4/family_governance_queue.tsv
data/material_master/governance_v0_4/cohort_001.tsv
data/material_master/governance_v0_4/cohort_001_material_master_preview.tsv
data/material_master/governance_v0_4/cohort_001_review_queue.tsv
```

执行与合并命令：

```powershell
python scripts\material_master\run_family_governance_cohort.py --cohort data\material_master\governance_v0_4\cohort_001.tsv --family-concurrency 3 --row-concurrency 2 --chunk-size 20
python scripts\material_master\build_family_governance_cohort_preview.py
```

浏览页选择“第一批多族治理预览”即可查看结果。该视图不会修改 `release_v1_0/material_master_release_v1_0.tsv`；独立复核发现的疑似重复保留在待人工确认队列，不自动合并。

## 标准名称字典与批量治理 v0.5

v0.5 不再逐 SKU 重写整张物料表，而是先治理正式发布表中的“物料名称”，形成稳定的四级结构：

```text
一级类目 -> 二级物料族 -> 三级标准物料名称 -> 四级 SKU 属性
```

PostgreSQL 保存批次状态、类型关系和冻结决定；Git 中的 TSV 是供人审查和回滚的快照。生成模型与独立复核模型都同意、且程序校验通过的物料族才会冻结。旧名称过于宽泛或需要拆分时，第二阶段会读取该名称下的全部 SKU 逐条映射；证据不足或两次判断不一致的项目进入问题队列。

输出目录：

```text
data/material_master/governance_v0_5/material_type_dictionary.tsv
data/material_master/governance_v0_5/material_type_aliases.tsv
data/material_master/governance_v0_5/material_attribute_templates.tsv
data/material_master/governance_v0_5/material_name_decisions.tsv
data/material_master/governance_v0_5/sku_type_mapping.tsv
data/material_master/governance_v0_5/material_governance_issues.tsv
```

先运行单个物料族样板：

```powershell
python scripts\material_master\run_type_dictionary_governance.py --top-group 工具耗材 --material-family 钻头 --max-names 100 --concurrency 1
```

样板通过后增量运行全表：

```powershell
python scripts\material_master\run_type_dictionary_governance.py --all --max-names 100 --concurrency 5
```

重复运行会跳过来源哈希未变化且已冻结的物料族。需要重新生成某个已冻结族时显式使用 `--force`；需要复用已经保存的模型响应做本地重建时使用 `--reuse-responses`。

只刷新 PostgreSQL 导出的 TSV、网页数据和覆盖统计，不调用 DeepSeek：

```powershell
python scripts\material_master\run_type_dictionary_governance.py --export-only
```

中断批次可按批次编号恢复。若仅希望先保存已完成的名称级判断，并把待下钻 SKU 留入明确问题队列，可使用：

```powershell
python scripts\material_master\run_type_dictionary_governance.py --batch-id <BATCH_ID> --reuse-responses --defer-detailed
```

浏览页默认选择“标准名称字典 v0.5”，可查看旧名称、标准类型 ID、名称决定、双 AI 复核、程序校验和问题项。治理阶段只写治理数据库和预览文件，不修改正式发布表，也不写 ERPNext。
