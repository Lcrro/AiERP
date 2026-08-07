---
name: nexterp-capability-manual
description: Use Nexterp business capabilities through progressive guides and frozen operations.
---

# Nexterp 工作规约

1. 先使用工作台给出的可信身份卡。需要岗位职责、协作关系、当前项目、最近单据、待办或流程位置时，调用 `nexterp_load_work_context`，一次最多加载三类。
2. 调用 `nexterp_search_capabilities` 查找业务能力；可信 `intent_mode=read` 时只查只读能力，不得进入写能力。
3. 再调用 `nexterp_load_guide`，只加载当前节点和必要的下一层说明。
3. 项目、仓库、物料编码、单位和 ERPNext 单号必须交给 Nexterp Resolver；不得猜测真实主键。
4. 不得自行拼装或调用 ERPNext ToolCall。
5. 写操作必须先调用 `nexterp_prepare_operation`。缺信息或多候选时自然追问员工。
6. 收到 `needs_confirmation` 后停止规划并明确说明待确认内容。独立 OpenClaw 客户端可用返回的 `pending_id` 调用执行工具；Nexterp 工作台会隐藏执行工具，并由工作台确认按钮执行同一份冻结操作。
7. 最终回复中的单号、状态、数量和日期只能来自 Nexterp 的 ERPNext 回读结果。
9. 被拒绝、过期或失败时不得自行绕过；说明原因和下一步。能力检索最多扩大一次，第二次仍未命中就停止。
10. `op.material.search` 已同时查询候选与相关仓库库存。`inventory_status=available` 且候选库存为空或合计为 0 时，应明确回答当前库存为 0，不要再说“需要我继续查库存吗”。
11. 新物料先使用 `op.material.classify`。只有结果为 `new_sku` 且员工明确要求建档时，才加载 `op.material.create_item`；建档操作会在服务端重新分类、查重和生成编码。`existing_sku` 必须复用现有物料，`needs_input` 和 `needs_choice` 必须继续追问，`new_type_review` 必须交物料管理员处理。

## 批量采购物料准入

- 收到表格或多行采购需求时，先逐行保留来源行、原始名称、规格、数量和单位，不得擅自合并或丢行。
- 整批只做事实抽取；标准类型边界、已有 SKU 查重和准入队列由 Nexterp 决定。
- 结果分为：复用已有 SKU、在已有类型下新增 SKU、新增标准类型、需要员工补充或选择。
- 歧义行只追问影响采购选择的最少信息；不得为了填满字段编造品牌、型号、材质或性能。
- 现场员工不负责填写完整主数据。能够从企业标准 SKU 或标准类型共同默认值确定的系统属性必须自动补齐；采购包装单位与库存单位的换算延后到报价或收货阶段处理，不应阻塞准入。
- 批量分析不等于批量建档。任何后续新建 SKU、标准类型或采购单据都必须形成独立确认动作。

## 采购来源链

- 材料申请之后依次可以进入：询价、供应商报价、采购订单、采购收货、采购退货。
- 这些操作必须提供真实来源单据；先搜索能力并加载对应操作说明，不得凭经验猜操作 ID。
- 来源单据中的公司、物料、数量、单位和来源行由 Nexterp 实时回读。员工只补充当前步骤新增的事实，例如询价供应商、报价、交货日期、实收数量或退货原因。
- 整单转换可以省略明细；部分报价、下单、收货或退货必须使用 Nexterp 返回的来源明细行。
