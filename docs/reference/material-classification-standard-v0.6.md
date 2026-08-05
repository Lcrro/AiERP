# 新物料分类与建档判断标准 v0.6

## 目的

这套标准用于指导 Agent 面对一个从未录入或不确定的新物料时，稳定回答三个问题：

```text
它属于哪个一级类目？
它属于哪个物料族和标准物料名称？
它是已有 SKU、缺资料，还是应当新建 SKU / 新类型？
```

当前冻结字典覆盖：

```text
20 个一级类目
147 个物料族
766 个标准物料名称
1,979 个已映射 SKU
```

分类能力只分析，不修改正式物料表，也不写 ERPNext。

## 四级结构

### 一级类目

按企业管理边界分类，例如：

```text
管材管件阀门
紧固件与连接件
工具耗材
劳保防护
电气电料
```

一级类目不能使用品牌、项目名称、尺寸或临时用途。

### 二级物料族

按稳定的产品结构、主要功能或采购管理方式分类，例如：

```text
钻头
螺丝/螺栓
阀门
直接/接头
手套
```

同一物料族的物料通常可以共用一套核心属性模板。材质、颜色、直径和长度一般不应直接成为物料族。

### 三级标准物料名称

标准名称必须是采购人员能识别的稳定商品类型，并且有明确边界。例如：

```text
内六角螺丝
膨胀螺栓
二坑二槽钻头
麻花钻头
异径接头
球阀
```

以下内容通常应下沉为 SKU 属性，而不是另建标准名称：

```text
品牌
尺寸和口径
材质
颜色
包装数量
强度等级
表面处理
普通用途描述
```

当某个接口或结构直接决定兼容性、安装方式或采购替代关系时，可以成为标准名称的一部分。例如 `SDS-Plus / 二坑二槽` 与 `SDS-Max / 五坑` 不能混为同一类型。

### 四级 SKU

SKU 由“标准物料名称 + 影响采购选择和库存互换性的属性”唯一确定。例如：

```text
内六角螺丝
规格 M8*45；材质 碳钢；强度等级 12.9；表面处理 发黑
```

只有会导致不能互换、价格显著不同或质量用途不同的属性才参与 SKU 唯一性。纯说明性信息放入辅助属性。

## Agent 工作规约

Agent 只负责从员工原话提取事实，不负责临场创造分类标准。

必须提取或保留：

```text
原始叫法
用途
产品结构
兼容接口
材质
型号
尺寸、口径和长度
单位与包装
员工明确说出的品牌或标准
```

禁止行为：

```text
不能猜测员工未提供的材质、品牌、强度或型号
不能因为名称相似就忽略兼容接口
不能把品牌、尺寸或包装提升为类目
不能自行创建新的标准物料类型
不能绕过重复 SKU 检查
不能在分类阶段写入 ERPNext
```

Agent 调用 `op.material.classify` 时提交：

```json
{
  "operation_id": "op.material.classify",
  "request_id": "唯一请求号",
  "query": "SDS-Plus四坑冲击钻头 12x350mm",
  "attributes": {
    "interface": "SDS-Plus四坑",
    "diameter": "12mm",
    "length": "350mm",
    "material": "硬质合金"
  },
  "top_group_hint": "工具耗材",
  "material_family_hint": "钻头"
}
```

`top_group_hint` 和 `material_family_hint` 只是缩小候选的提示，不能覆盖字典边界。

## 结果状态

| 状态 | 含义 | Agent 下一步 |
| --- | --- | --- |
| `existing_sku` | 已唯一匹配现有 SKU | 返回现有编码，不重复建档 |
| `needs_choice` | 多个类型或 SKU 都合理 | 展示候选及差异，让员工选择 |
| `needs_input` | 类型已确定，但缺影响采购选择的属性 | 只追问缺失属性 |
| `new_sku` | 类型和属性完整，未发现重复 SKU | 准备新 SKU 建档，不自动创建 |
| `new_type_review` | 现有字典无可靠类型 | 交物料管理员审核是否新增类型 |

## 示例

### 已有 SKU

```text
输入：SDS-Plus 四坑冲击钻头，12*350mm，硬质合金
标准名称：二坑二槽钻头
结果：existing_sku / TOOL-000328
```

### 缺资料

```text
输入：内六角螺丝 M9*47
标准名称：内六角螺丝
缺失：材质
结果：needs_input
```

### 新 SKU

```text
输入：内六角螺丝 M9*47，碳钢，12.9级，发黑
标准名称：内六角螺丝
重复检查：未发现相同 SKU
结果：new_sku
```

### 新类型审核

```text
输入：现有字典完全无法解释的新型产品
结果：new_type_review
```

## 权威来源

分类程序读取：

```text
data/material_master/governance_v0_5/material_type_dictionary.tsv
data/material_master/governance_v0_5/material_type_aliases.tsv
data/material_master/governance_v0_5/material_attribute_templates.tsv
data/material_master/governance_v0_5/sku_type_mapping.tsv
data/material_master/release_v1_0/material_master_release_v1_0.tsv
```

AI 的知识和提示只能帮助提取事实与解释结果，不能覆盖这些冻结数据和程序校验。
