---
name: nexterp-capability-manual
description: Use Nexterp business capabilities through progressive guides and frozen operations.
---

# Nexterp 工作规约

1. 先调用 `nexterp_search_capabilities` 查找业务能力。
2. 再调用 `nexterp_load_guide`，只加载当前节点和必要的下一层说明。
3. 项目、仓库、物料编码、单位和 ERPNext 单号必须交给 Nexterp Resolver；不得猜测真实主键。
4. 不得自行拼装或调用 ERPNext ToolCall。
5. 写操作必须先调用 `nexterp_prepare_operation`。缺信息或多候选时自然追问员工。
6. 收到 `needs_confirmation` 后，用返回的 `pending_id` 调用 `nexterp_execute_prepared_operation`，由 OpenClaw 显示权威确认框。
7. 最终回复中的单号、状态、数量和日期只能来自 Nexterp 的 ERPNext 回读结果。
8. 被拒绝、过期或失败时不得自行绕过；说明原因和下一步。

## 采购来源链

- 材料申请之后依次可以进入：询价、供应商报价、采购订单、采购收货、采购退货。
- 这些操作必须提供真实来源单据；先搜索能力并加载对应操作说明，不得凭经验猜操作 ID。
- 来源单据中的公司、物料、数量、单位和来源行由 Nexterp 实时回读。员工只补充当前步骤新增的事实，例如询价供应商、报价、交货日期、实收数量或退货原因。
- 整单转换可以省略明细；部分报价、下单、收货或退货必须使用 Nexterp 返回的来源明细行。
