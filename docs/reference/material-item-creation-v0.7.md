# 标准物料建档 v0.7

## 目的

本能力把分类结果中的 `new_sku` 安全地转换为 ERPNext `Item`，但不允许 Agent 直接填写物料编码、物料组或最终建档字段。

```text
员工描述新物料
→ op.material.classify
→ 冻结字典判断类型、属性和重复 SKU
→ 仅 new_sku 进入 op.material.create_item
→ 服务端重新分类和查重
→ 生成编码、名称、物料组和单位
→ 检查 ERPNext 依赖
→ 展示不可修改的确认卡
→ 员工确认
→ 以员工本人权限创建 Item
→ 回读核对
```

分类能力永远不写 ERPNext。建档能力也不会相信模型此前给出的分类结论，而是使用同一冻结字典重新计算。

## 状态边界

| 分类状态 | 建档行为 |
| --- | --- |
| `existing_sku` | 返回现有编码，不创建重复物料 |
| `needs_choice` | 展示类型或 SKU 候选，等待员工选择 |
| `needs_input` | 只追问影响采购和库存互换性的缺失属性 |
| `new_sku` | 允许准备建档确认卡 |
| `new_type_review` | 交物料管理员审查字典，不自动创造新类型 |

## 字段来源

| 字段 | 来源 | 是否允许 Agent 决定 |
| --- | --- | --- |
| 原始描述 | 员工输入 | 只能忠实提取 |
| 已确认属性 | 员工输入与多轮确认 | 只能使用标准属性键 |
| `type_id` | 冻结标准名称字典 Resolver | 否 |
| `item_code` | 确定性编码器 | 否 |
| `item_name` | 标准名称 + 影响 SKU 唯一性的属性 | 否 |
| `item_group` | 同一标准类型的发布目录 | 否 |
| `stock_uom` | 员工明确单位或同类型稳定单位 | 否 |

上述 7 个字段及其来源、控件、约束已经登记在 PostgreSQL 的 `operation_slot` 中。跨字段规则登记在 `operation_rule` 中。

## ToolCall 边界

底层专用工具为：

```text
erpnext.stock.create_item
```

它只接受标准 `Item` 字段白名单，不接受任意文档载荷。风险级别为 `L3`，必须确认；仅物料设备管理和系统管理策略可使用。仓库、项目及普通员工不能因为拥有库存查询权限而获得物料建档权限。

确认动作冻结以下信息：

```text
员工身份
会话
目录修订
标准类型
物料编码
SKU 名称
物料组
库存单位
规格
ToolCall 哈希
过期时间
```

确认后执行原 ToolCall，不重新让模型规划或改参。

## 回读验收

ERPNext 返回成功不等于建档完成。服务必须重新读取 `Item`，核对：

```text
item_code
item_name
item_group
stock_uom
```

任一字段不一致时返回验证失败，不得向员工宣称创建成功。

## 当前验收

- 真实 Capability API 已完成一次无写入预览。
- 示例“内六角螺丝 M9*47，碳钢，8.8 级，镀锌”生成 `FAST-000124` 确认卡。
- 真实 ERPNext 已确认目标 Item Group 和 UOM 存在。
- 预览停在 `needs_confirmation`，未创建 Item；临时待确认记录已清理。
- Python 全量测试 `498 passed`，Tool Schema 与 Adapter handler 为 `161 / 161`。

## 工作台接入 v0.8

员工工作台现在可以直接发起标准物料建档请求。Agent 仍只负责理解原话和提取事实，工作台显示的确认卡来自 Capability API 冻结结果，包含：

```text
标准类型
物料编码
SKU 名称
ERPNext 物料组
库存单位
必填规格
辅助规格
```

用户确认后执行同一个 `pending_id`，不重新让模型规划。成功后工作台可直接读取并展示 ERPNext `Item`，不跳转到 ERPNext 原生页面。

真实无写入验收使用“内六角螺丝 M9×61，碳钢，8.8级，镀锌”，生成 `FAST-000124` 确认卡并停在确认阶段；临时待确认记录随后清理，ERPNext 中没有创建测试 Item。

本阶段同时修复了隔离 OpenClaw Profile 的插件部署问题：安装脚本现在总是在 `npm pack` 前重新构建 TypeScript，防止旧 `dist` 的 Tool Schema 拒绝新增的 `attributes` 字段。

独立测试入口：

```text
http://127.0.0.1:8788/material-item-lab
```

该页面默认使用材料设备主管测试身份，提供完整新 SKU、接口规格、缺失规格和疑似重复四类样例。发送只运行预览；只有冻结确认卡真正生成后才显示“确认创建”。右侧同时展示可审计步骤和完整结果 JSON，便于定位分类、说明书、参数修复或 ERPNext 回读问题。
