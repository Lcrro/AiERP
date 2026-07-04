# 螺丝族治理样板 v0.2

## 1. 范围和边界

本样板只生成治理候选，不改正式主表、不写 ERPNext、不改浏览器 HTML/JSON。它不是最终导入表。候选表共 213 行，其中 `scope_type=in_family` 是当前物料族本来就是“螺丝”的 84 条，`scope_type=boundary_sample` 是被螺丝、螺栓、螺母、垫片、膨胀、花篮/花兰、螺丝刀、取出器、套件/组件等关键词带入的边界样本 129 条。

螺丝族的边界原则：普通螺丝/螺栓可以统一到“螺丝”族；膨胀螺丝归膨胀锚栓；花篮/花兰螺丝归索具拉紧器；螺丝刀和取出器归工具；螺母、垫片/垫圈、螺杆分开；套件/组件先保留成套属性并进入人工确认。

## 2. action 统计

| action | 数量 |
|---|---:|
| keep_as_kit_review | 34 |
| keep_screw | 51 |
| move_to_expansion_anchor | 27 |
| move_to_nut | 18 |
| move_to_screw_rod | 9 |
| move_to_tool | 13 |
| move_to_turnbuckle | 7 |
| move_to_washer | 14 |
| needs_manual_review | 40 |

## 3. 标准名称规则

- 普通螺丝、普通螺栓、自攻螺丝、钻尾螺丝、鱼尾螺丝、骑马螺丝：标准名称建议统一为“螺丝”。
- 内六角、六角、十字、圆头、T型、自攻、钻尾、全牙、高强度、不锈钢、镀锌：不作为族名，进入规格属性或搜索别名。
- 螺丝套件、螺丝组件、螺栓组件：标准名称建议为“螺丝套件”，但必须确认套件组成。
- 原始 item_name 保留在别名/搜索词中，便于历史采购检索。

## 4. 规格模板

螺丝族建议必填字段：规格、头型/驱动、材质、强度等级、表面处理。条件必填字段包括螺纹形式、套件组成、包装数量、是否定制/图纸号。字段映射详见 `data/material_master/governance_v0_2/screw/screw_spec_template.json`。

当前数据最常见的问题是：规格有但未确认是否为 M 制；材质、强度等级、头型/驱动、表面处理缺失；单位“套”与真正的套件/组件混在一起。

## 5. 可以规则/脚本处理

- P0 长词优先：膨胀螺丝、花篮/花兰螺丝、螺丝刀/取出器、螺杆、螺母、垫片/垫圈先于普通螺丝命中。
- 属性抽取：内六角、六角、十字、圆头、自攻、钻尾、全牙、不锈钢、镀锌可抽成候选属性。
- 字段同义词：螺丝规格/规格、头型/类型、表面/表面处理、包含/套件组成可规则归一。
- 标准名称候选：普通螺丝/螺栓统一成“螺丝”，套件/组件统一成“螺丝套件”候选。

## 6. 必须人工确认

- 单位“套”是包装单位，还是包含螺母、平垫、弹垫的成套 SKU。
- 螺丝组件/套件是否作为独立成套 SKU 管理，是否允许拆分为螺丝、螺母、垫片。
- 原始 8*30、10*40、14*50 等规格是否等同 M8*30、M10*40、M14*50。
- 材质缺失时是否可默认碳钢，强度等级缺失时是否可默认历史常用等级。
- 不锈钢是否需要细分 201/304/316；高强度、加长、定制类是否需要图纸号。

## 7. 下一步如何应用到正式主表

1. 先由负责人验收 `screw_rule_proposals.tsv` 中 P0 规则，确认边界词和排除词。
2. 对 `screw_manual_review_queue.tsv` 逐行补齐人工答案，特别是套件组成、单位口径、材质和强度等级。
3. 生成下一版候选修正表，包含标准名称、目标物料族、规格字段、单位建议和质量等级建议。
4. 经业务确认后，再由正式导入流程更新主表；本样板本身不直接写 ERPNext。

## 8. 如何复用到其他物料族

这套样板可以复用于后续高优先级物料族，但每个族都必须保留 `scope_type` 和拆分表，避免把边界样本误当成族内物料。

- 液压接头：`in_family` 为当前液压接头；`boundary_sample` 应纳入高压接头、油管接头、对丝、铜接头、气动接头、消防接头、直接/接头。规则重点是液压/气动/水暖/消防/定制加工边界，owner policy 重点是高压是否足以判定液压。
- 钻头：`in_family` 为当前钻头；`boundary_sample` 应纳入冲击钻、钻夹头、钻尾螺丝、批头、开孔器。规则重点是钻头本体与工具整机/附件边界，模板重点是直径、长度、柄型、适用材质。
- 管件：`in_family` 可按直接/接头、弯头、三通等分别治理；`boundary_sample` 应纳入液压接头、气动接头、消防接头、法兰、卡箍、定制管路接头。规则重点是系统归属、材质、连接方式和口径。
- 手套：`in_family` 为当前手套；`boundary_sample` 应纳入扳手套筒、手套箱、手套机等误命中词。规则重点是劳保手套本体与设备/工具词排除，模板重点是材质、工艺、防护用途、尺码、厚度和长度。

复用流程建议：先定义族内样本和边界关键词，再产出候选全集、族内治理表、边界复核表、规格模板、规则提案、人工队列和 summary；最后再进入业务确认。

## 9. 本轮产物

- `data/material_master/governance_v0_2/screw/screw_governance_candidates.tsv`
- `data/material_master/governance_v0_2/screw/screw_family_governed.tsv`
- `data/material_master/governance_v0_2/screw/screw_boundary_review.tsv`
- `data/material_master/governance_v0_2/screw/screw_spec_template.json`
- `data/material_master/governance_v0_2/screw/screw_rule_proposals.tsv`
- `data/material_master/governance_v0_2/screw/screw_manual_review_queue.tsv`
- `data/material_master/governance_v0_2/screw/screw_governance_summary.json`
