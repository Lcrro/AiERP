# 税则到 Nexterp 物料族映射审阅包 v0.1

## 目的

`tariff-nodes.jsonl` 是 2026 年公开税则的结构化候选目录，不是 Nexterp 的 ERPNext Item Group。此步骤只生成内部物料族映射候选，供业务审阅；不发布、不创建标准类型、不写入 ERPNext。

## 输入与输出

使用坐标列解析得到的 8 位税号节点作为输入，读取现有 `material_master_release_v1_1.tsv` 的物料族集合做边界校验。输出目录为 `data/material_master/tariff_family_review_v0_1/`：

- `tariff_family_candidates.tsv`：每个 8 位税号一行，保留原名称、归一化名称、直接父级六位子目及名称、HS 章号、建议一级类目、建议物料族、匹配规则、置信度和审阅状态。
- `tariff_family_summary.json`：行数、章节分布、候选物料族分布以及未映射/歧义样例。
- `tariff_family_rules.json`：当前可解释规则快照，便于版本化审阅。
- `tariff_family_decisions.tsv`：空白人工决策模板；每行必须明确 `approve`、`reject` 或 `revise`。
- `tariff_family_decisions.tsv.meta.json`：模板绑定的候选包 SHA-256，防止基于旧候选包冻结。

## 状态含义

- `candidate`：唯一最高优先级规则命中，且建议物料族存在于本地物料主数据；仍需业务确认。
- `ambiguous`：多个物料族同时命中，不能自动选择。
- `unmapped`：尚未建立足够可靠的内部映射规则。

关键词规则只看税号叶节点名称，父级名称只作为审阅证据。这样不会把“其他”或包含多个实物的混合税目强行归入某个物料族。HS 编码可作为来源与检索键，但不能替代 Nexterp 的物料族边界、标准类型和 SKU 属性规则。

## 生成命令

```powershell
python scripts/material_master/build_tariff_family_review.py `
  --input .runtime/tariff-extraction/<job_id>/tariff-nodes.jsonl `
  --output data/material_master/tariff_family_review_v0_1

python scripts/material_master/freeze_tariff_family_review.py template `
  --candidates data/material_master/tariff_family_review_v0_1/tariff_family_candidates.tsv `
  --output data/material_master/tariff_family_review_v0_1/tariff_family_decisions.tsv
```

业务人员填写决策表后，只有显式 `approve` 且填写审阅人、一级类目和已存在的内部物料族，才会进入冻结审阅版本：

```powershell
python scripts/material_master/freeze_tariff_family_review.py freeze `
  --candidates data/material_master/tariff_family_review_v0_1/tariff_family_candidates.tsv `
  --decisions data/material_master/tariff_family_review_v0_1/tariff_family_decisions.tsv `
  --output data/material_master/tariff_family_review_v0_1/frozen_release_v0_1
```

冻结目录包含 `tariff_family_release.tsv`、`tariff_family_decision_audit.tsv` 和 `manifest.json`。它的状态是 `review_only_frozen`，不是 ERPNext 发布版；未填写决策的税号不会进入冻结表，旧模板或不存在的内部物料族会被拒绝。

针对紧固件，可先生成小范围审阅队列（HS 7317/7318/7415，共 20 行），避免在全量目录中查找：

```powershell
python scripts/material_master/build_tariff_family_review_slice.py `
  --candidates data/material_master/tariff_family_review_v0_1/tariff_family_candidates.tsv `
  --output data/material_master/tariff_family_review_v0_1/fastener_review_v0_2 `
  --prefix 7317 --prefix 7318 --prefix 7415
```

切片目录同时生成自己的决策模板和哈希绑定文件。当前切片中 16 行有确定性候选，`73181900`、`74152900`、`74153390` 和 `74153900` 保持未映射，不能因为同属紧固件章节就自动归入螺丝族。

在物料族候选之外，可从同一份切片生成“来源证据属性候选”。它只提取税则叶节点和父级名称中明确出现的强度、头型、螺纹形态、紧固件种类和材质证据，不补猜缺失规格；混合税目或只来自父级的证据会标为 `review_required`：

```powershell
python scripts/material_master/build_tariff_attribute_review.py `
  --input data/material_master/tariff_family_review_v0_1/fastener_review_v0_2/tariff_family_candidates.tsv `
  --output data/material_master/tariff_family_review_v0_1/fastener_review_v0_2
```

输出 `tariff_attribute_candidates.tsv` 和 `tariff_attribute_summary.json`。例如 `73181510` 会保留 `抗拉强度 >=800 MPa`、`螺钉 | 螺栓` 以及“钢铁制（来源父级证据）”，但整行仍是待审阅候选。属性候选不等同于标准类型/SKU 属性，也不会直接写入 ERPNext；必须在业务确认物料族、标准名称和必填属性后，才能进入物料准入闭环。

`http://127.0.0.1:8788/tariff-family-review` 会自动读取该属性候选包，在表格增加“来源属性证据”列，并提供“属性待审”筛选。页面决策仍只保存在当前浏览器；下载的 `tariff_family_decisions.tsv` 会附带 `attribute_status` 和 `attributes` 列，冻结脚本只消费既有的物料族决策字段，不会把属性证据误当成已批准属性。

属性列还支持本地 `approve / reject / revise`、确认/修改属性文本和备注，另行导出 `tariff_attribute_decisions.tsv`。这是人工确认草稿，不是冻结发布文件；后续编译器必须校验属性决定、候选包哈希和物料族决定后，才允许形成标准类型/SKU候选。

也可以使用命令行生成和校验哈希绑定的属性决定模板：

```powershell
python scripts/material_master/freeze_tariff_attribute_review.py template `
  --candidates data/material_master/tariff_family_review_v0_1/fastener_review_v0_2/tariff_attribute_candidates.tsv `
  --output data/material_master/tariff_family_review_v0_1/fastener_review_v0_2/tariff_attribute_decisions.tsv

python scripts/material_master/freeze_tariff_attribute_review.py freeze `
  --candidates data/material_master/tariff_family_review_v0_1/fastener_review_v0_2/tariff_attribute_candidates.tsv `
  --decisions data/material_master/tariff_family_review_v0_1/fastener_review_v0_2/tariff_attribute_decisions.tsv `
  --output data/material_master/tariff_family_review_v0_1/fastener_review_v0_2/attribute_frozen_release_v0_1
```

`freeze` 要求 `.meta.json` 中的候选 SHA-256 与当前候选表一致，且每个决定都有审阅人；`revise` 必须提供备注和合法 JSON 属性覆盖。冻结包仍是 `review_only_frozen`。物料族冻结包和属性冻结包都准备好后，才可生成标准类型/SKU候选：

```powershell
python scripts/material_master/freeze_tariff_attribute_review.py compile `
  --family-release data/material_master/tariff_family_review_v0_1/fastener_review_v0_2/frozen_release_v0_1/tariff_family_release.tsv `
  --attribute-release data/material_master/tariff_family_review_v0_1/fastener_review_v0_2/attribute_frozen_release_v0_1/tariff_attribute_release.tsv `
  --output data/material_master/tariff_family_review_v0_1/fastener_review_v0_2/standard_type_sku_candidates_v0_1
```

编译结果中的 `candidate_status=ready_for_manual_confirmation` 仍不是 ERPNext Item，也不会自动生成编码、创建标准类型或同步库存系统。

当前包由 `d183eee797344deb9e3918c0baab48b4` 任务生成。源目录包含 21 类、96 章、1,228 个四位品目、5,612 个六位子目和 8,972 个八位税号；重建审阅包后仍是 142 个确定性候选、3 个歧义项、8,827 个未映射项。任何后续“批准映射”都必须另行产生冻结版本，并在物料准入闭环中显式确认后才允许创建标准类型/SKU、同步 ERPNext 和回读验证。
