# 物料 SKU 治理提示词 v0.3

## 目标

把旧采购清单里的脏 SKU 明细整理成一批可导入 ERPNext 的初始物料主数据。

本任务不是还原历史采购真相，而是生成一张干净、可搜索、可选择、可追溯的初始物料清单。旧清单只是参考来源。

## 四级结构

```text
一级类目 -> 二级物料族 -> 三级物料名称 -> 四级 SKU 明细
```

示例：

```text
管材管件阀门 -> 弯头 -> 弯头 -> 弯头 PPR 25
紧固件与连接件 -> 螺丝/螺栓 -> 内六角螺丝 -> 内六角螺丝 M8*45
```

三级物料名称只保留商品类型，不塞材质、品牌、连接方式、尺寸。

## 输出字段

```text
item_code
standard_item_name
standard_sku_name
minimal_required_specs
standard_uom
brand
aliases
removed_default_fields
default_fill_basis
merge_group
merge_reason
source_item_code
governance_reason
```

## 核心规则

- `standard_sku_name` 使用“物料名称 + 最关键规格”，让采购员一眼看懂买什么。
- `minimal_required_specs` 只保留会导致买错/买对的字段。
- 行业默认且不会造成误解的字段不进入 SKU 名称和最小规格。
- 接口、口径、长度、角度、异径、大小头、压力等级、电流等级、强度等级必须保留。
- 别名/土名进入 `aliases`，不参与唯一 SKU 判断。
- 原始信息缺失时，可以生成合理初始 SKU，但必须在 `default_fill_basis` 说明依据。
- 不输出 `unresolved`、`manual_check`、`needs_review`、`quality`、`policy` 或放行等级字段。

## 公元纠错

本项目历史清单里的“公元”通常是老员工把“公称”写错，不是品牌。

处理规则：

```text
公元DN50 -> 公称直径：DN50
公元25 -> 规格/口径：25
品牌：公元 -> 按公称/口径纠正，不进入 brand
```

`公元` 不得输出到：

```text
brand
aliases
removed_default_fields
minimal_required_specs
standard_sku_name
```

## 品牌规则

真正的品牌/厂牌进入 `brand` 字段，例如：

```text
埃美柯
世达
得力
```

品牌默认不进入 `standard_sku_name` 或 `minimal_required_specs`，除非：

- 是指定品牌件；
- 是设备兼容件；
- 品牌会明显影响安装或使用兼容性。

## 默认字段删除

可以删除的字段：

```text
PPR 直接默认热熔
PVC/UPVC 直接默认胶粘或承插
普通直通形态
普通弯头形态
不影响采购选择的泛化描述
```

不能删除的字段：

```text
25*4分
2寸*150mm
DN50*DN25
内丝/外丝
45度/90度
压力等级
电流等级
强度等级
```

## 重复合并

如果多个历史 `item_code` 生成同一个：

```text
standard_sku_name + minimal_required_specs
```

则视为同一标准 SKU。

合并后：

- 保留一个 `canonical_item_code`；
- 旧编码放入 `merged_from_item_codes`；
- 单位冲突不拆分 SKU，统一成标准单位，并记录来源单位。

## 示例

### 直接/直通

输入：

```text
PPR25直接
```

输出：

```text
standard_sku_name: PPR直接 25
minimal_required_specs: 材质：PPR；规格/口径：25
standard_uom: 个
```

### 弯头

输入：

```text
公元PPR25弯头
```

输出：

```text
standard_sku_name: 弯头 PPR 25
minimal_required_specs: 材质：PPR；规格/口径：25；角度：90度
brand:
default_fill_basis: 公元按公称误写处理；角度未指定，默认90度
```

### 内牙弯头

输入：

```text
PPR25*4分内牙弯头
```

输出：

```text
standard_sku_name: 弯头 PPR 25*4分 内牙
minimal_required_specs: 材质：PPR；规格/口径：25*4分；接口：内丝；角度：90度
```

### 球阀

输入：

```text
埃美柯DN50不锈钢球阀
```

输出：

```text
standard_sku_name: 球阀 DN50 不锈钢
minimal_required_specs: 公称直径：DN50；材质：不锈钢
brand: 埃美柯
```

## 当前实现

调用脚本：

```text
scripts/material_master/deepseek_sku_governance_trial.py
scripts/material_master/run_deepseek_sku_governance_batch.py
scripts/material_master/merge_sku_governance_duplicates.py
```

当前样板批次：

```text
outputs/material_master/sku_governance/batch_pipe_valve_gongcheng_fix_complete_20260703/unique_all.tsv
outputs/material_master/sku_governance/batch_pipe_valve_gongcheng_fix_complete_20260703/duplicates_all.tsv
```
