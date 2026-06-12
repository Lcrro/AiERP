# 小型土木公司一日运转模拟：ToolCall 覆盖矩阵

本文把“一天事件流”拆成当前 ToolCall 能力、缺口和下一步验收项。目标不是证明系统已经完成，而是明确哪些事件可以立即用现有工具跑，哪些还需要业务封装或端到端沙盘测试。

关联文档：

- [时间顺序事件流](civil-company-day-events.md)
- [员工角色表](civil-company-day-roles.md)
- [ToolCall 五大模块控制矩阵](../reference/toolcall-five-module-control-matrix.md)

## 覆盖状态定义

| 状态 | 含义 |
|---|---|
| 可执行 | 已有专用 ToolCall 或通用 ToolCall 能完成该动作，且语义边界清楚。 |
| 部分可执行 | 已有底层 ToolCall，但缺业务封装、确认策略、端到端测试或专用摘要。 |
| 缺口 | 目前只能靠人工页面操作、裸 `call_method`，或还没有明确安全工具。 |

## 事件覆盖矩阵

| 时间 | 事件 | 当前状态 | 可用 ToolCall | 主要缺口 | 下一步验收 |
|---|---|---|---|---|---|
| 08:00 | 管理层查看今日异常 | 部分可执行 | `tool:erpnext.run_report`、`tool:erpnext.search_documents`、`tool:erpnext.stock.get_balance`、`tool:erpnext.buying.run_purchase_analysis`、`tool:erpnext.projects.get_project_cost_context`、`tool:erpnext.accounting.accounts_payable`、`tool:erpnext.call_method` | 还没有专用“管理层每日异常摘要”ToolCall；当前 `agent_bridge.api.get_manager_exceptions` 只能通过通用 method 调用。 | 新增管理摘要 wrapper，或把该 method 纳入正式 Tool schema；用真实沙盘数据生成一页日报。 |
| 08:20 | 城东项目提报劳保用品需求 | 可执行 | `tool:erpnext.search_items`、`tool:erpnext.buying.create_material_request_draft` | 自然语言 Agent Runtime 未接入；项目、仓库、需求日期需要从用户上下文补齐。 | 用“马超说人话”创建城东项目 Material Request 草稿。 |
| 08:35 | 南区项目提报管材管件需求 | 可执行 | `tool:erpnext.search_items`、`tool:erpnext.buying.create_material_request_draft` | 规格不清时需要追问策略；管材类物料重复和规格治理还未完成。 | 对缺口径/材质/压力等级的需求返回追问，不创建错误草稿。 |
| 08:50 | 西站项目提报电气耗材需求 | 可执行 | `tool:erpnext.search_items`、`tool:erpnext.buying.create_material_request_draft` | 电气物料能检索，但还没有岗位级默认仓库/项目上下文。 | 创建含热缩管、胶布、断路器的 Material Request 草稿。 |
| 09:10 | 项目经理审核材料需求 | 部分可执行 | `tool:erpnext.get_document`、`tool:erpnext.buying.submit_document`、`tool:erpnext.apply_workflow`、`tool:erpnext.get_workflow_actions` | 提交动作有确认门槛；没有“项目经理审核材料申请”业务封装。 | 对 MR 执行提交前校验，缺项目/仓库/日期时阻断。 |
| 09:30 | 采购汇总待处理材料申请 | 部分可执行 | `tool:erpnext.search_documents`、`tool:erpnext.buying.search_suppliers`、`tool:erpnext.buying.search_item_prices`、`tool:erpnext.buying.get_supplier_procurement_profile` | 没有“待采购材料申请工作台”专用 ToolCall；分组逻辑需要固化。 | 查询 Pending MR，按项目、物料组、供应商候选、紧急程度输出清单。 |
| 10:00 | 常用品直接转采购订单 | 可执行 | `tool:erpnext.get_document`、`tool:erpnext.buying.create_purchase_order_from_material_request_draft`、`tool:erpnext.buying.submit_document` | MR 必须先提交；runner 还没把上一步 MR 编号自动传给 PO wrapper。 | 在 runner 中提交 MR 后生成 PO 草稿，确认 MR 行引用保留。 |
| 10:30 | 管材类材料发起询价 | 可执行 | `tool:erpnext.buying.create_request_for_quotation_draft`、`tool:erpnext.buying.create_supplier_quotation_draft`、`tool:erpnext.buying.compare_supplier_quotations`、`tool:erpnext.buying.search_suppliers` | 自动发送 RFQ 邮件尚未实现；报价中标动作尚未封装。 | 创建 RFQ 草稿、录入两个供应商报价草稿、比较报价。 |
| 11:20 | 中心仓检查可用库存 | 可执行 | `tool:erpnext.stock.get_balance`、`tool:erpnext.stock.get_item_locations`、`tool:erpnext.stock.get_ledger_entries`、`tool:erpnext.stock.allocate_shortages` | 还没有按项目需求自动判定“采购/调拨/发料”的业务编排。 | 针对 MR 行查询中心仓和项目仓库存，输出建议动作。 |
| 13:30 | 供应商送来劳保用品 | 可执行 | `tool:erpnext.buying.create_purchase_receipt_from_purchase_order_draft`、`tool:erpnext.buying.submit_document`、`tool:erpnext.stock.verify_purchase_receipt_stock_impact`、`tool:erpnext.stock.get_document_impact` | PR 提交会影响库存，需要确认策略；runner 还没把上一步 PO 编号自动传给 PR wrapper。 | 在 runner 中提交 PO 后生成 PR 草稿，确认 PO 行引用保留，并验证入库数量/价值影响。 |
| 14:00 | 到货规格不符 | 可执行 | `tool:erpnext.stock.create_quality_inspection_draft`、`tool:erpnext.buying.record_purchase_receipt_discrepancy`、`tool:erpnext.buying.get_purchase_receipt_return_context`、`tool:erpnext.buying.create_purchase_receipt_return_draft`、`tool:erpnext.stock.list_quality_inspections` | 退货提交仍需确认策略；质检提交策略后续可再细化。 | 创建质检草稿，记录到货差异、创建跟进 ToDo、返回退货预览；确认后再创建退货草稿。 |
| 14:30 | 项目仓领料 | 可执行 | `tool:erpnext.projects.get_material_issue_context`、`tool:erpnext.projects.create_material_issue_draft`、`tool:erpnext.stock.submit_document`、`tool:erpnext.projects.verify_material_issue_cost_impact` | 项目、成本中心、仓库绑定规则还没固化；提交库存移动需要确认。 | 按项目和仓库创建 Material Issue 草稿，缺料时阻断；提交后验证项目领料成本影响。 |
| 15:10 | 缺料触发补采 | 部分可执行 | `tool:erpnext.stock.get_balance`、`tool:erpnext.stock.allocate_shortages`、`tool:erpnext.buying.generate_purchase_suggestions`、`tool:erpnext.buying.create_material_request_draft`、`tool:erpnext.create_todo` | 缺主动监控/定时触发；补采建议到 MR 的编排未验收。 | 用库存不足样例生成补采建议和采购 ToDo。 |
| 16:00 | 财务处理采购发票 | 可执行 | `tool:erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft`、`tool:erpnext.accounting.prepare_invoice_taxes`、`tool:erpnext.accounting.accounts_payable`、`tool:erpnext.accounting.submit_financial_document` | 发票提交会产生财务影响，需要 L5 财务确认；runner 还没把上一步已提交 PR 编号自动传给 PI wrapper。 | 在 runner 中提交 PR 后生成 PI 草稿，确认 PR/PO 行引用保留。 |
| 16:40 | 采购跟进未到货订单 | 部分可执行 | `tool:erpnext.search_documents`、`tool:erpnext.buying.run_purchase_analysis`、`tool:erpnext.create_todo`、`tool:erpnext.add_comment` | 缺“逾期采购订单跟进清单”专用 ToolCall。 | 查询逾期 PO，按供应商生成跟进 ToDo。 |
| 17:20 | 项目经理查看项目成本 | 可执行 | `tool:erpnext.projects.get_project_cost_context`、`tool:erpnext.projects.verify_material_issue_cost_impact`、`tool:erpnext.stock.get_item_lifecycle_summary`、`tool:erpnext.accounting.general_ledger`、`tool:erpnext.accounting.financial_report` | 管理口径还需最终确认；项目预算、领料、采购收货、发票之间的归集规则需要固化。 | 输出某项目当日领料、采购、退货、发票的成本摘要。 |
| 18:00 | 总经理看当天收尾摘要 | 部分可执行 | `tool:erpnext.run_report`、`tool:erpnext.search_documents`、`tool:erpnext.projects.get_project_cost_context`、`tool:erpnext.accounting.accounts_payable`、`tool:erpnext.buying.run_purchase_analysis`、`tool:erpnext.call_method` | 与 08:00 相同，缺正式管理日报 ToolCall 和端到端聚合测试。 | 用当天沙盘数据输出采购、库存、项目、财务、异常闭环日报。 |

## 当前结论

现有工具层已经覆盖多数底层 ERPNext 动作：

- 物料检索和材料申请草稿
- RFQ、供应商报价、采购订单、采购收货、采购退货草稿
- 库存余额、库存流水、缺料分配、库存移动草稿、质检草稿、采购收货库存影响验证、物料生命周期摘要
- 项目领料上下文、项目领料草稿、项目领料成本影响验证
- 采购发票和付款草稿
- ToDo、评论、通用查询、报表

但还不能声明“一日业务完整自动跑通”，原因是：

- 很多能力停留在草稿工具，提交需要确认策略。
- 从上游单据自动生成下游单据的引用关系还没端到端验收。
- 管理层日报、待采购工作台、逾期采购跟进仍缺专用业务 wrapper。
- 已建立可重复执行的 scenario seed 脚本，但尚未建立 scenario run 脚本。

## 优先补齐清单

| 优先级 | 缺口 | 目标 |
|---|---|---|
| P0 | 沙盘基础数据脚本 | 已完成：创建项目、仓库、供应商、测试员工和初始库存，见 [Sandbox 初始化](civil-company-day-seed.md)。 |
| P0 | 事件流自动化 runner | 已有第一版：按关键事件执行 ToolCall，默认 dry-run 跳过写入，见 [Sandbox 初始化](civil-company-day-seed.md)。 |
| P1 | 材料申请转采购订单 wrapper | 已完成：从已提交 Material Request 创建 Purchase Order 草稿，保留源单引用；还需 runner 端到端验收。 |
| P1 | 待采购工作台 wrapper | 汇总 Pending Material Request，按项目、供应商、紧急程度分组。 |
| P1 | 采购订单转采购收货 wrapper | 已完成：从已提交 Purchase Order 创建 Purchase Receipt 草稿，保留源单引用；还需 runner 端到端验收。 |
| P1 | 采购收货转采购发票 wrapper | 已完成：从已提交 Purchase Receipt 创建 Purchase Invoice 草稿，保留 PR/PO 行引用；还需 runner 端到端验收。 |
| P1 | 到货差异记录 wrapper | 已完成：记录规格不符、质检意见、退货建议，并创建评论/ToDo；本地 smoke 已在 `MAT-PRE-2026-00007` 上验证。 |
| P1 | 物料生命周期缺口 ToolCall | 已完成：补齐质检草稿、采购收货库存影响验证、项目领料成本影响验证、物料生命周期摘要。 |
| P1 | 逾期采购跟进 wrapper | 查询逾期 PO，生成供应商跟进清单。 |
| P2 | 管理层日报 wrapper | 聚合采购、库存、项目、财务异常，输出稳定结构。 |
| P2 | 项目成本口径固化 | 明确项目成本来自领料、采购收货、采购发票还是 GL。 |

## 验收路线

第一步不新增工具，先做可重复沙盘：

```text
seed master data
-> run material request events
-> run procurement events
-> run stock receipt/return events
-> run project issue events
-> run accounting draft events
-> generate manager summary
```

第二步只在沙盘跑不通的位置补业务 wrapper，避免继续堆泛用 ToolCall。
