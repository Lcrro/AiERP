# GPC 2026-05 参考目录整合 v0.1

## 范围

工作台 `/tariff-taxonomy-browser` 现在可以在 HS《中华人民共和国进出口税则（2026）》与 GS1 GPC `2026-05` 之间一键切换。两者均为本机内部只读参考目录；本功能不写入 ERPNext，不调用 Agent，不做 GTIN/GDSN 查询，也不建立 HS、GPC 与物料族之间的映射。

## 数据来源与导入

导入命令：

```powershell
python scripts/material_master/import_gpc_reference.py --version 2026-05
```

导入器只接受 GS1 官方 HTTPS 域名，使用版本页返回的 Current GPC standard full package。包内 Combined Published Schema XML 是主输入，Excel Schema 是数量交叉核验输入；解压过程拒绝 `..`、绝对路径和运行期目录越界。

运行期目录（已被 Git 忽略）：

```text
.runtime/gpc-reference/2026-05/
  source-package.zip
  package/
  nodes.jsonl
  brick-profiles.jsonl
  translations.zh-CN.jsonl
  profile-translations.zh-CN.jsonl
  profile-text-translations.zh-CN.jsonl
  manifest.json
  audit.json
```

真实导入核验基线：45 Segment、162 Family、938 Class、5,318 Brick；2,085 个唯一属性、13,733 个唯一属性值。XML 与 Excel 的六组数量交叉核验均通过，父级缺失、重复编码、孤立 Brick 和循环引用均为 0。

GPC 官方英文名称和定义原文保留不变。`translations.zh-CN.jsonl` 以源文本 SHA-256 绑定工作译名；缺失翻译在界面显示英文并标记“中文待补”。`--translate` 会关闭 thinking、设置长输出预算并校验编码覆盖；对于全量名称，实测更稳定的方式是 `--translate-batch-size 1500`，必要时只重试缺失批次，避免重复翻译已完成内容。网络、凭据或响应截断只会保留回退英文，不阻塞目录导入。

目录节点名称翻译完成后，可单独补齐 Brick 详情中的 Attribute 与 Attribute Value 名称：

```powershell
python scripts/material_master/translate_gpc_profile_terms.py --version 2026-05 --batch-size 1500 --min-batch-size 125
```

`profile-translations.zh-CN.jsonl` 保存 2,085 个属性名和 13,733 个属性值名的中文工作译名。任务按编码去重、按官方英文 SHA-256 绑定、逐批落盘且可重复运行；工作台以“中文 / 官方英文”展示。2026-05 全量结果为 15,818/15,818，缺失、重复编码、源哈希不一致和官方名称不一致均为 0。

Brick 的 Definition、Includes 与 Excludes 使用独立命令翻译：

```powershell
python scripts/material_master/translate_gpc_profile_texts.py --version 2026-05 --max-batch-characters 100000 --min-batch-characters 12500
```

程序按官方原文 SHA-256 去重，同一段原文始终复用同一译文；逐批写入 `profile-text-translations.zh-CN.jsonl` 并支持断点续跑。2026-05 共 15,829 个字段实例，去重为 10,004 段，减少 5,825 次重复翻译；DeepSeek V4-Flash 37 个请求失败 0，最终 10,004/10,004、缺失 0。译文还会检查中文字符、源哈希、原文一致性、元话术和严重截断。工作台默认显示中文正文，官方英文保存在“查看官方英文”折叠区，不覆盖权威原文。

## 目录模型

官方 GPC 只展示四层：`Segment → Family → Class → Brick`。Brick 的定义、Includes、Excludes、Attribute 和 Attribute Value 在详情面板展示，不伪造成第五层目录节点。

确实没有合适官方 Brick、但内部采购必须建类的物料，可以通过版本化文件 `data/material_master/gpc_internal_extensions_v0_1.json` 声明内部节点。官方节点保持 8 位，每新增一层就在父编码后追加两位 `01–99`；同时以 `is_gpc=false`、`catalog_origin=nexterp` 和 `classification_source` 保存隐性溯源。内部节点不计入 GS1 的 6,463 个官方节点，也不会冒充 GPC 数据。实际物料统一挂在标准类型层；例如“灭火器箱”编号为 `9103030001`，挂在官方 Class `91030300 家庭/企业灭火器` 下。

统一只读接口：

```text
GET /api/reference-catalog/summary?catalog=hs|gpc
GET /api/reference-catalog/children?catalog=hs|gpc&parent_code=...
GET /api/reference-catalog/search?catalog=hs|gpc&q=...&kind=...&limit=...
GET /api/reference-catalog/profile?catalog=hs|gpc&code=...
```

GPC 搜索同时索引目录节点、Attribute 和 Attribute Value 的编码、中英文工作名称及定义。属性术语不会伪造成目录层级：搜索结果以一个聚合术语展示引用次数、Brick 数量和前 24 个引用位置；点击引用后跳转到对应 Brick，并高亮具体属性或属性值。例如 `30002654` 返回“是 / YES”，全量基线为 1,062 个 Brick、1,963 个属性引用。

## 实际物料挂载与空目录过滤

已整理的内部物料候选保存在 Git 忽略的运行期文件：

```text
.runtime/material-master/gpc-material-placements.jsonl
```

每项记录包含内部物料编号、标准类型、标准化名称、官方 GPC Brick 或已声明内部末级编码、分类来源、库存单位、完整状态、规格依据、来源行，以及三组精简字段：`procurement_attributes`（采购必选）、`price_drivers`（明显影响价格或适配）和 `gpc_notes`（分类边界）。三组都必须非空，但不是制造商规格书：采购必选最多 4 条、价格/适配最多 3 条、分类提示最多 3 条。颜色、品牌、玻管直径、杆体材质、安装附件等只有在现场必须指定、会显著改变价格/适配，或参考目录明确用来区分类别时才保留。

加载器只允许物料挂到有效官方 Brick 或已声明的 Nexterp 内部末级；内部物料必须显式记录 `classification_source=nexterp_internal`。重复编号、缺失关键字段、超过精简上限、非“完整”状态、仍有待确认问题或直接挂到 Segment/Family/Class 的记录都会被拒绝。原始记录缺少规格时，可在用户明确授权后采用现场最常见的可采购规格；规格依据保留在运行期数据用于审计，但不在采购卡上重复展示。今后采购不同规格时新增独立物料。物料仍是业务对象，不伪造成目录的额外层级；末级详情显示物料卡，所有祖先节点只显示聚合物料数。

`children` 和 `search` 接口支持 `materialized_only=true`。启用后，服务端仅返回有实际物料的官方 Brick/内部末级及其完整祖先链，工作台的“隐藏无实际物料目录”开关会同步更新官方四层计数、左侧根目录和懒加载树。标准化物料名、类型及已整理属性也进入末级搜索文本。当前运行期为 79 项候选、68 个类型档案，分布在 45 个官方 Brick 和 1 个内部末级；筛选后的官方节点为 14 Segment、18 Family、27 Class、45 Brick，另显示 1 个内部末级。

运行期物料和内部扩展只用于内部整理；本页没有发布按钮，不创建 ERPNext Item，也不改变 GPC 官方目录数据。

实际物料进一步通过[施工采购模板与稀疏 SKU 框架 v0.1](procurement-template-framework-v0.1.md)分配主模板、叠加约束和属性角色。当前框架固定为 10 份主模板与 5 份约束，不按 GPC Brick 人工复制模板；SKU 只为真实发生的身份属性组合生成候选，定制加工品优先保留为项目配置。

旧的 `/api/tariff-taxonomy/*` 接口继续保留，旧 HS `#code=` 书签继续可用。新的 URL 使用 `?catalog=hs|gpc#code=...`；每个来源分别保存展开节点、选中节点、层级筛选和滚动位置。

## 运行期审计

`manifest.json` 记录来源 URL、版本、原始 ZIP SHA-256、生成时间、输入文件、层级数量和翻译状态；`audit.json` 记录父级、重复、孤立、循环和 Excel 交叉核验结果。原始包和派生全量数据不提交仓库。
