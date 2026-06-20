# ToolCall Data Dictionary

本文由结构化契约自动生成，源数据来自：

- `ERPNext_TOOL_SCHEMAS`：代码里的 ToolCall JSON Schema。
- `ToolAccessPolicy`：岗位工具门禁。
- `config/tool_contracts/*.yaml`：按模块维护的业务约束、Resolver、Repair 和底层映射。

本文不是权限系统本身。真正执行时仍由 `ToolGateway` 做工具门禁，由 ERPNext 后端做最终权限裁决。

## 总览

- Tool schema 数：150
- Tool contract 数：150
- 覆盖状态：完整

### 按 Expose 统计

| Expose | 数量 |
|---|---:|
| `agent_visible` | 130 |
| `developer_only` | 6 |
| `runtime_internal` | 14 |

### 按 Confirm 统计

| Confirm | 数量 |
|---|---:|
| `admin_confirm` | 5 |
| `financial_confirm` | 2 |
| `none` | 82 |
| `submit_confirm` | 11 |
| `supervisor_confirm` | 2 |
| `user_confirm` | 48 |

### 按风险等级统计

| 风险等级 | 数量 |
|---|---:|
| `L0` | 71 |
| `L1` | 12 |
| `L2` | 5 |
| `L3` | 43 |
| `L4` | 11 |
| `L5_ADMIN` | 6 |
| `L5_FINANCIAL` | 2 |

## 字段口径

| 字段 | 说明 |
|---|---|
| ToolCall | 完整工具名。 |
| 用途 | 业务用途和风险等级。 |
| Allowed Roles | 哪些岗位 profile 可以直接使用。 |
| Expose | `agent_visible`、`runtime_internal`、`developer_only`。 |
| 核心入参 | 参数名、类型、必填、来源、Resolver、约束。 |
| Confirm | 是否需要强确认。 |
| Repair | 失败或不确定时的修复策略。 |
| Backend Mapping | 对应 ERPNext DocType、Report、Frappe Method 或 agent_bridge 方法。 |
| 权限裁决 | ToolGateway 先判断工具可用性，ERPNext 后端做最终业务权限裁决。 |

## 全量总表

| ToolCall | 风险 | Expose | Allowed Roles | Confirm | Backend Mapping |
|---|---|---|---|---|---|
| `erpnext.get_logged_user` | `L0` | `agent_visible` | 仓管、采购、项目经理、班组长、财务、资产管理员、管理层、系统管理员 | `none` | - |
| `erpnext.search_documents` | `L0` | `runtime_internal` | Runtime | `none` | DocType: `任意 DocType` |
| `erpnext.search_items` | `L0` | `agent_visible` | 仓管、采购、项目经理、班组长、财务、资产管理员、管理层、系统管理员 | `none` | DocType: `Item` |
| `erpnext.count_documents` | `L0` | `runtime_internal` | Runtime | `none` | DocType: `任意 DocType`<br>Method: `frappe.client.get_count` |
| `erpnext.get_document` | `L0` | `runtime_internal` | Runtime | `none` | DocType: `任意 DocType` |
| `erpnext.create_document` | `L3` | `developer_only` | developer | `user_confirm` | DocType: `任意 DocType` |
| `erpnext.update_document` | `L3` | `developer_only` | developer | `user_confirm` | DocType: `任意 DocType` |
| `erpnext.delete_document` | `L4` | `developer_only` | developer | `submit_confirm` | DocType: `任意 DocType` |
| `erpnext.document_exists` | `L0` | `runtime_internal` | Runtime | `none` | DocType: `任意 DocType` |
| `erpnext.resolve_link` | `L0` | `runtime_internal` | Runtime | `none` | DocType: `任意 Link 目标 DocType` |
| `erpnext.validate_fields` | `L0` | `runtime_internal` | Runtime | `none` | DocType: `DocType Meta` |
| `erpnext.get_doctype_schema` | `L0` | `runtime_internal` | Runtime | `none` | DocType: `DocType Meta` |
| `erpnext.submit_document` | `L4` | `runtime_internal` | Runtime | `submit_confirm` | DocType: `任意可提交 DocType`<br>Method: `agent_bridge.api.submit_document` |
| `erpnext.cancel_document` | `L4` | `runtime_internal` | Runtime | `submit_confirm` | DocType: `任意可取消 DocType`<br>Method: `agent_bridge.api.cancel_document` |
| `erpnext.amend_document` | `L4` | `runtime_internal` | Runtime | `submit_confirm` | - |
| `erpnext.get_workflow_actions` | `L0` | `runtime_internal` | Runtime | `none` | - |
| `erpnext.apply_workflow` | `L4` | `runtime_internal` | Runtime | `submit_confirm` | Method: `frappe.model.workflow.apply_workflow` |
| `erpnext.run_report` | `L0` | `runtime_internal` | Runtime | `none` | - |
| `erpnext.users.list_users` | `L0` | `agent_visible` | 系统管理员 | `none` | DocType: `User` |
| `erpnext.users.get_user_access_summary` | `L0` | `agent_visible` | 系统管理员 | `none` | DocType: `User`, `User Permission` |
| `erpnext.users.list_roles` | `L0` | `agent_visible` | 系统管理员 | `none` | DocType: `Role` |
| `erpnext.users.list_role_profiles` | `L0` | `agent_visible` | 系统管理员 | `none` | DocType: `Role Profile` |
| `erpnext.users.preview_role_profile_roles` | `L0` | `agent_visible` | 系统管理员 | `none` | DocType: `Role Profile`, `Role` |
| `erpnext.users.list_user_permissions` | `L0` | `agent_visible` | 系统管理员 | `none` | DocType: `User Permission` |
| `erpnext.users.list_shared_documents` | `L0` | `agent_visible` | 系统管理员 | `none` | DocType: `DocShare` |
| `erpnext.users.list_access_logs` | `L0` | `agent_visible` | 系统管理员 | `none` | DocType: `Access Log` |
| `erpnext.users.list_activity_logs` | `L0` | `agent_visible` | 系统管理员 | `none` | DocType: `Activity Log` |
| `erpnext.users.get_permission_metadata` | `L0` | `agent_visible` | 系统管理员 | `none` | DocType: `DocType Meta`<br>Method: `ERPNextClient.get_doctype_schema` |
| `erpnext.users.preview_effective_permissions` | `L0` | `agent_visible` | 系统管理员 | `none` | DocType: `User`, `DocType Meta`, `User Permission` |
| `erpnext.users.check_server_permission` | `L0` | `agent_visible` | 系统管理员 | `none` | DocType: `User`, `DocType Meta`<br>Method: `agent_bridge.api.check_user_permission` |
| `erpnext.users.preview_permission_policy_change` | `L5_ADMIN` | `agent_visible` | 系统管理员 | `none` | DocType: `DocType Meta` |
| `erpnext.users.create_user_draft` | `L5_ADMIN` | `agent_visible` | 系统管理员 | `admin_confirm` | DocType: `User`, `Role`<br>Method: `ERPNextClient.create_document` |
| `erpnext.users.set_user_enabled` | `L5_ADMIN` | `agent_visible` | 系统管理员 | `admin_confirm` | DocType: `User`<br>Method: `ERPNextClient.update_document` |
| `erpnext.users.assign_roles` | `L5_ADMIN` | `agent_visible` | 系统管理员 | `admin_confirm` | DocType: `User`, `Role`<br>Method: `ERPNextClient.update_document` |
| `erpnext.users.create_user_permission` | `L5_ADMIN` | `agent_visible` | 系统管理员 | `admin_confirm` | DocType: `User Permission`, `User`<br>Method: `ERPNextClient.create_document` |
| `erpnext.users.delete_user_permission` | `L5_ADMIN` | `agent_visible` | 系统管理员 | `admin_confirm` | DocType: `User Permission`<br>Method: `ERPNextClient.delete_document` |
| `erpnext.accounting.search_accounts` | `L0` | `agent_visible` | 财务 | `none` | DocType: `Account`<br>只读 search_documents；默认按 lft asc 返回科目树。 |
| `erpnext.accounting.search_cost_centers` | `L0` | `agent_visible` | 财务 | `none` | DocType: `Cost Center`<br>只读 search_documents；默认按 lft asc 返回成本中心树。 |
| `erpnext.accounting.search_budgets` | `L0` | `agent_visible` | 财务 | `none` | DocType: `Budget` |
| `erpnext.accounting.search_fiscal_years` | `L0` | `agent_visible` | 财务 | `none` | DocType: `Fiscal Year` |
| `erpnext.accounting.search_accounting_periods` | `L0` | `agent_visible` | 财务 | `none` | DocType: `Accounting Period` |
| `erpnext.accounting.search_payment_terms` | `L0` | `agent_visible` | 财务 | `none` | DocType: `Payment Term`, `Payment Terms Template` |
| `erpnext.accounting.search_tax_templates` | `L0` | `agent_visible` | 财务 | `none` | DocType: `Sales Taxes and Charges Template`, `Purchase Taxes and Charges Template` |
| `erpnext.accounting.get_report_filters` | `L0` | `agent_visible` | 财务、管理层 | `none` | DocType: `Report`<br>Report: `General Ledger`, `Accounts Receivable`, `Accounts Payable`, `Trial Balance`, `Balance Sheet`, `Profit and Loss Statement`, `Cash Flow` |
| `erpnext.accounting.general_ledger` | `L0` | `agent_visible` | 财务、管理层 | `none` | Report: `General Ledger`<br>run_report 只读；必填 company。 |
| `erpnext.accounting.accounts_receivable` | `L0` | `agent_visible` | 财务、管理层 | `none` | Report: `Accounts Receivable`<br>run_report 只读；必填 company。 |
| `erpnext.accounting.accounts_payable` | `L0` | `agent_visible` | 财务、管理层 | `none` | Report: `Accounts Payable`<br>run_report 只读；必填 company。 |
| `erpnext.accounting.financial_report` | `L0` | `agent_visible` | 财务、管理层 | `none` | Report: `Trial Balance`, `Balance Sheet`, `Profit and Loss Statement`, `Cash Flow`<br>run_report 只读；必填 company。 |
| `erpnext.accounting.create_journal_entry_draft` | `L3` | `agent_visible` | 财务 | `user_confirm` | DocType: `Journal Entry`, `Journal Entry Account` |
| `erpnext.accounting.create_payment_entry_draft` | `L3` | `agent_visible` | 财务 | `user_confirm` | DocType: `Payment Entry`, `Payment Entry Reference` |
| `erpnext.accounting.create_sales_invoice_draft` | `L3` | `agent_visible` | 财务 | `user_confirm` | DocType: `Sales Invoice`, `Sales Invoice Item`, `Sales Taxes and Charges` |
| `erpnext.accounting.create_purchase_invoice_draft` | `L3` | `agent_visible` | 财务 | `user_confirm` | DocType: `Purchase Invoice`, `Purchase Invoice Item`, `Purchase Taxes and Charges` |
| `erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft` | `L3` | `agent_visible` | 财务 | `user_confirm` | DocType: `Purchase Receipt`, `Purchase Receipt Item`, `Purchase Invoice`, `Purchase Invoice Item`<br>先读取 Purchase Receipt，校验可开票数量，再创建 Purchase Invoice 草稿。 |
| `erpnext.accounting.create_period_closing_voucher_draft` | `L3` | `agent_visible` | 财务 | `user_confirm` | DocType: `Period Closing Voucher` |
| `erpnext.accounting.prepare_payment_allocation` | `L1` | `agent_visible` | 财务 | `none` | DocType: `Sales Invoice`, `Purchase Invoice`<br>读取已提交且未结清的发票，返回分配建议。 |
| `erpnext.accounting.prepare_invoice_taxes` | `L1` | `agent_visible` | 财务 | `none` | DocType: `Sales Taxes and Charges Template`, `Purchase Taxes and Charges Template`<br>可读取税费模板并根据输入明细准备 taxes 行；最终总额仍由 ERPNext 草稿创建校验。 |
| `erpnext.accounting.prepare_bank_reconciliation` | `L1` | `agent_visible` | 财务 | `none` | DocType: `Bank Transaction`, `Payment Entry`<br>只读读取 Bank Transaction 与已提交 Payment Entry 候选。 |
| `erpnext.accounting.apply_bank_reconciliation` | `L5_FINANCIAL` | `agent_visible` | 财务 | `financial_confirm` | DocType: `Bank Transaction`, `Payment Entry`<br>Method: `agent_bridge.api.reconcile_bank_transaction` |
| `erpnext.accounting.create_budget_draft` | `L3` | `agent_visible` | 财务 | `user_confirm` | DocType: `Budget`, `Budget Account` |
| `erpnext.accounting.update_budget_draft` | `L3` | `agent_visible` | 财务 | `user_confirm` | DocType: `Budget`, `Budget Account` |
| `erpnext.accounting.submit_financial_document` | `L5_FINANCIAL` | `agent_visible` | 财务 | `financial_confirm` | DocType: `Journal Entry`, `Payment Entry`, `Sales Invoice`, `Purchase Invoice`, `Period Closing Voucher`<br>仅提交白名单财务 DocType。 |
| `erpnext.assets.search_assets` | `L0` | `agent_visible` | 资产管理员 | `none` | DocType: `Asset` |
| `erpnext.assets.search_asset_categories` | `L0` | `agent_visible` | 资产管理员 | `none` | DocType: `Asset Category` |
| `erpnext.assets.search_asset_locations` | `L0` | `agent_visible` | 资产管理员 | `none` | DocType: `Asset Location` |
| `erpnext.assets.get_financial_snapshot` | `L0` | `agent_visible` | 资产管理员 | `none` | DocType: `Asset`, `Asset Depreciation Schedule` |
| `erpnext.assets.get_depreciation_schedule` | `L0` | `agent_visible` | 资产管理员 | `none` | DocType: `Asset Depreciation Schedule` |
| `erpnext.assets.create_asset_draft` | `L3` | `agent_visible` | 资产管理员 | `user_confirm` | DocType: `Asset`<br>Method: `ERPNextClient.create_document` |
| `erpnext.assets.create_movement_draft` | `L3` | `agent_visible` | 资产管理员 | `user_confirm` | DocType: `Asset Movement`<br>Method: `ERPNextClient.create_document` |
| `erpnext.assets.create_maintenance_draft` | `L3` | `agent_visible` | 资产管理员 | `user_confirm` | DocType: `Asset Maintenance`<br>Method: `ERPNextClient.create_document` |
| `erpnext.assets.create_maintenance_log_draft` | `L3` | `agent_visible` | 资产管理员 | `user_confirm` | DocType: `Asset Maintenance Log`<br>Method: `ERPNextClient.create_document` |
| `erpnext.assets.create_repair_draft` | `L3` | `agent_visible` | 资产管理员 | `user_confirm` | DocType: `Asset Repair`<br>Method: `ERPNextClient.create_document` |
| `erpnext.assets.create_value_adjustment_draft` | `L3` | `agent_visible` | 资产管理员 | `user_confirm` | DocType: `Asset Value Adjustment`<br>Method: `ERPNextClient.create_document` |
| `erpnext.assets.prepare_disposal_or_sale` | `L1` | `agent_visible` | 资产管理员 | `supervisor_confirm` | DocType: `Asset`<br>该工具只读取 Asset 并准备处置/销售风险上下文，实际过账或销售由财务/销售受控工具处理。 |
| `erpnext.assets.submit_document` | `L4` | `agent_visible` | 资产管理员 | `submit_confirm` | DocType: `Asset`, `Asset Movement`, `Asset Maintenance`, `Asset Maintenance Log`, `Asset Repair`, `Asset Value Adjustment`<br>Method: `agent_bridge.api.submit_document` |
| `erpnext.stock.get_balance` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Bin`, `Item`, `Warehouse`<br>主要读取 Bin，必要时关联 Item 与 Warehouse。 |
| `erpnext.stock.get_item_locations` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Bin`, `Item`, `Warehouse` |
| `erpnext.stock.get_ledger_entries` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Stock Ledger Entry`, `Item`, `Warehouse` |
| `erpnext.stock.get_stock_settings` | `L0` | `agent_visible` | 仓管、仓库主管、管理层 | `none` | DocType: `Stock Settings` |
| `erpnext.stock.resolve_item` | `L1` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Item`, `Item Group`<br>可选使用 PostgreSQL material catalog 召回，再以 ERPNext Item 为最终候选。 |
| `erpnext.stock.create_entry_draft` | `L3` | `agent_visible` | 仓管、仓库主管 | `user_confirm` | DocType: `Stock Entry`, `Stock Entry Detail`, `Item`, `Warehouse`, `Batch`, `Serial No`, `UOM` |
| `erpnext.stock.create_reconciliation_draft` | `L3` | `agent_visible` | 仓管、仓库主管 | `supervisor_confirm` | DocType: `Stock Reconciliation`, `Stock Reconciliation Item`, `Item`, `Warehouse`, `Batch`, `Serial No` |
| `erpnext.stock.search_batches` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Batch`, `Item` |
| `erpnext.stock.list_batch_balances` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Batch`, `Stock Ledger Entry`, `Item`, `Warehouse` |
| `erpnext.stock.search_serial_numbers` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Serial No`, `Item`, `Warehouse` |
| `erpnext.stock.create_batch` | `L3` | `agent_visible` | 仓管、仓库主管 | `user_confirm` | DocType: `Batch`, `Item` |
| `erpnext.stock.update_batch` | `L4` | `agent_visible` | 仓库主管 | `submit_confirm` | DocType: `Batch` |
| `erpnext.stock.create_serial_no` | `L3` | `agent_visible` | 仓管、仓库主管 | `user_confirm` | DocType: `Serial No`, `Item`, `Warehouse` |
| `erpnext.stock.update_serial_no` | `L4` | `agent_visible` | 仓库主管 | `submit_confirm` | DocType: `Serial No` |
| `erpnext.stock.list_pick_lists` | `L0` | `agent_visible` | 仓管、仓库主管、项目经理、班组长、管理层 | `none` | DocType: `Pick List` |
| `erpnext.stock.create_pick_list_draft` | `L3` | `agent_visible` | 仓管、仓库主管 | `user_confirm` | DocType: `Pick List`, `Pick List Item`, `Item`, `Warehouse`, `Batch`, `Serial No`, `UOM` |
| `erpnext.stock.list_reservations` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Stock Reservation Entry`, `Item`, `Warehouse` |
| `erpnext.stock.create_reservation_draft` | `L3` | `agent_visible` | 仓管、仓库主管 | `user_confirm` | DocType: `Stock Reservation Entry`, `Item`, `Warehouse`, `UOM` |
| `erpnext.stock.preview_valuation` | `L1` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Item`, `Warehouse`, `Stock Ledger Entry`<br>通过 agent_bridge 预览，不写入 Stock Entry 或 Stock Reconciliation。 |
| `erpnext.stock.allocate_shortages` | `L1` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Item`, `Warehouse`, `Bin`<br>通过 agent_bridge 计算可用量和短缺量。 |
| `erpnext.stock.list_delivery_notes` | `L0` | `agent_visible` | 仓管、仓库主管、项目经理、班组长、管理层 | `none` | DocType: `Delivery Note` |
| `erpnext.stock.list_purchase_receipts` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、管理层 | `none` | DocType: `Purchase Receipt` |
| `erpnext.stock.get_document_impact` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Delivery Note`, `Purchase Receipt`, `Stock Ledger Entry` |
| `erpnext.stock.list_item_reorders` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、管理层 | `none` | DocType: `Item Reorder`, `Item`, `Warehouse` |
| `erpnext.stock.list_quality_inspections` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Quality Inspection`, `Item` |
| `erpnext.stock.create_quality_inspection_draft` | `L3` | `agent_visible` | 仓管、仓库主管 | `user_confirm` | DocType: `Quality Inspection`, `Quality Inspection Reading`, `Item` |
| `erpnext.stock.verify_purchase_receipt_stock_impact` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、管理层 | `none` | DocType: `Purchase Receipt`, `Stock Ledger Entry`, `Item`, `Warehouse` |
| `erpnext.stock.get_item_lifecycle_summary` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、管理层 | `none` | DocType: `Item`, `Purchase Receipt Item`, `Stock Ledger Entry`, `Quality Inspection`, `Stock Entry Detail`, `Purchase Invoice Item`, `Warehouse` |
| `erpnext.stock.list_warehouses` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Warehouse`, `Company` |
| `erpnext.stock.create_warehouse` | `L3` | `agent_visible` | 仓库主管 | `user_confirm` | DocType: `Warehouse`, `Company` |
| `erpnext.stock.update_warehouse` | `L3` | `agent_visible` | 仓库主管 | `user_confirm` | DocType: `Warehouse`, `Company` |
| `erpnext.stock.list_item_groups` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `Item Group` |
| `erpnext.stock.create_item_group` | `L3` | `agent_visible` | 仓库主管 | `user_confirm` | DocType: `Item Group` |
| `erpnext.stock.update_item_group` | `L3` | `agent_visible` | 仓库主管 | `user_confirm` | DocType: `Item Group` |
| `erpnext.stock.list_uoms` | `L0` | `agent_visible` | 仓管、仓库主管、采购、项目经理、班组长、管理层 | `none` | DocType: `UOM` |
| `erpnext.stock.create_uom` | `L3` | `agent_visible` | 仓库主管 | `user_confirm` | DocType: `UOM` |
| `erpnext.stock.update_uom` | `L3` | `agent_visible` | 仓库主管 | `user_confirm` | DocType: `UOM` |
| `erpnext.stock.submit_document` | `L4` | `agent_visible` | 仓库主管 | `submit_confirm` | DocType: `Stock Entry`, `Stock Reconciliation`, `Delivery Note`, `Purchase Receipt`, `Pick List`, `Stock Reservation Entry` |
| `erpnext.projects.get_project_cost_context` | `L0` | `agent_visible` | 项目经理、班组长、管理层 | `none` | DocType: `Project`, `Task`, `Stock Entry`, `Purchase Receipt` |
| `erpnext.projects.get_material_issue_context` | `L1` | `agent_visible` | 项目经理、班组长 | `none` | DocType: `Project`, `Bin`, `Item`, `Warehouse`<br>读取 Project 并通过库存余额接口检查源仓可用量。 |
| `erpnext.projects.create_material_issue_draft` | `L3` | `agent_visible` | 项目经理、班组长 | `user_confirm` | DocType: `Project`, `Stock Entry`, `Stock Entry Detail`, `Item`, `Warehouse`, `Cost Center`<br>Method: `ERPNextClient.create_stock_entry_draft` |
| `erpnext.projects.verify_material_issue_cost_impact` | `L0` | `agent_visible` | 项目经理、班组长、管理层 | `none` | DocType: `Stock Entry`, `Stock Entry Detail`, `Stock Ledger Entry`, `Project` |
| `erpnext.setup_item_master` | `L3` | `developer_only` | developer | `user_confirm` | - |
| `erpnext.prepare_item_from_intent` | `L0` | `runtime_internal` | Runtime | `none` | - |
| `erpnext.create_item_from_intent` | `L3` | `developer_only` | developer | `user_confirm` | - |
| `erpnext.create_todo` | `L2` | `agent_visible` | 仓管、采购、项目经理、班组长、财务、资产管理员、管理层、系统管理员 | `user_confirm` | DocType: `ToDo` |
| `erpnext.add_comment` | `L2` | `agent_visible` | 仓管、采购、项目经理、班组长、财务、资产管理员、管理层、系统管理员 | `user_confirm` | DocType: `Comment`<br>Method: `frappe.desk.form.utils.add_comment` |
| `erpnext.get_comments` | `L0` | `agent_visible` | 仓管、采购、项目经理、班组长、财务、资产管理员、管理层、系统管理员 | `none` | - |
| `erpnext.assign_to` | `L2` | `agent_visible` | 仓管、采购、项目经理、班组长、财务、资产管理员、管理层、系统管理员 | `user_confirm` | DocType: `ToDo`<br>Method: `frappe.desk.form.assign_to.add` |
| `erpnext.clear_assignment` | `L3` | `agent_visible` | 仓管、采购、项目经理、班组长、财务、资产管理员、管理层、系统管理员 | `user_confirm` | - |
| `erpnext.attach_file` | `L2` | `agent_visible` | 仓管、采购、项目经理、班组长、财务、资产管理员、管理层、系统管理员 | `user_confirm` | - |
| `erpnext.list_attachments` | `L0` | `agent_visible` | 仓管、采购、项目经理、班组长、财务、资产管理员、管理层、系统管理员 | `none` | - |
| `erpnext.delete_attachment` | `L4` | `agent_visible` | 仓管、采购、项目经理、班组长、财务、资产管理员、系统管理员 | `submit_confirm` | DocType: `File` |
| `erpnext.call_method` | `L1` | `developer_only` | developer | `user_confirm` | Method: `任意已允许 Frappe Method` |
| `erpnext.buying.search_suppliers` | `L0` | `agent_visible` | 采购、仓管、项目经理、班组长、管理层 | `none` | DocType: `Supplier`<br>Method: `search_documents`<br>只读 Supplier 安全字段，按名称、分组、类型和冻结/禁用状态过滤。 |
| `erpnext.buying.search_supplier_scorecards` | `L0` | `agent_visible` | 采购、管理层 | `none` | DocType: `Supplier Scorecard`<br>Method: `search_documents` |
| `erpnext.buying.get_supplier_procurement_profile` | `L1` | `agent_visible` | 采购、管理层 | `none` | DocType: `Supplier`, `Supplier Scorecard`, `Item Supplier`, `Item Price`<br>Method: `get_document`, `search_documents` |
| `erpnext.buying.create_supplier_group_draft` | `L3` | `agent_visible` | 采购、管理层 | `user_confirm` | DocType: `Supplier Group`<br>Method: `create_document` |
| `erpnext.buying.create_supplier_draft` | `L3` | `agent_visible` | 采购、管理层 | `user_confirm` | DocType: `Supplier`<br>Method: `create_document` |
| `erpnext.buying.create_material_request_draft` | `L3` | `agent_visible` | 采购、项目经理、班组长 | `user_confirm` | DocType: `Material Request`, `Material Request Item`<br>Method: `create_document` |
| `erpnext.buying.create_request_for_quotation_draft` | `L3` | `agent_visible` | 采购 | `user_confirm` | DocType: `Request for Quotation`, `Request for Quotation Supplier`, `Request for Quotation Item`<br>Method: `create_document` |
| `erpnext.buying.create_supplier_quotation_draft` | `L3` | `agent_visible` | 采购 | `user_confirm` | DocType: `Supplier Quotation`, `Supplier Quotation Item`<br>Method: `create_document` |
| `erpnext.buying.create_purchase_order_draft` | `L3` | `agent_visible` | 采购 | `user_confirm` | DocType: `Purchase Order`, `Purchase Order Item`<br>Method: `create_document` |
| `erpnext.buying.create_purchase_order_from_material_request_draft` | `L3` | `agent_visible` | 采购 | `user_confirm` | DocType: `Material Request`, `Material Request Item`, `Purchase Order`, `Purchase Order Item`<br>Method: `get_document`, `create_document`<br>先读取 Material Request 并校验 docstatus/type/剩余可订购数量，再创建 Purchase Order 草稿。 |
| `erpnext.buying.create_purchase_receipt_draft` | `L3` | `agent_visible` | 仓管、采购 | `user_confirm` | DocType: `Purchase Receipt`, `Purchase Receipt Item`<br>Method: `create_document` |
| `erpnext.buying.create_purchase_receipt_from_purchase_order_draft` | `L3` | `agent_visible` | 仓管、采购 | `user_confirm` | DocType: `Purchase Order`, `Purchase Order Item`, `Purchase Receipt`, `Purchase Receipt Item`<br>Method: `get_document`, `create_document`<br>先读取 Purchase Order 并校验 docstatus/status/剩余可收货数量，再创建 Purchase Receipt 草稿。 |
| `erpnext.buying.record_purchase_receipt_discrepancy` | `L2` | `agent_visible` | 仓管、采购、项目经理 | `user_confirm` | DocType: `Purchase Receipt`, `Comment`, `ToDo`<br>Method: `get_document`, `add_comment`, `create_todo`<br>会写入审计可追溯评论；prepare_return 只生成退货预览上下文，不创建退货单。 |
| `erpnext.buying.get_purchase_receipt_return_context` | `L1` | `agent_visible` | 仓管、采购、管理层 | `none` | DocType: `Purchase Receipt`, `Purchase Receipt Item`<br>Method: `get_document` |
| `erpnext.buying.create_purchase_receipt_return_draft` | `L3` | `agent_visible` | 仓管、采购 | `user_confirm` | DocType: `Purchase Receipt`, `Purchase Receipt Item`<br>Method: `get_document`, `create_document`<br>复用退货上下文校验，创建 is_return=1 且 return_against 指向原采购收货单的草稿。 |
| `erpnext.buying.generate_purchase_suggestions` | `L0` | `agent_visible` | 采购、仓管、项目经理、管理层 | `none` | DocType: `Item`, `Bin`, `Material Request`<br>Method: `agent_bridge.api.generate_purchase_suggestions`<br>调用桥接业务逻辑生成建议结果，本工具不创建采购单据。 |
| `erpnext.buying.search_item_suppliers` | `L0` | `agent_visible` | 采购、管理层 | `none` | DocType: `Item Supplier`, `Item`, `Supplier`<br>Method: `search_documents` |
| `erpnext.buying.search_item_prices` | `L0` | `agent_visible` | 采购、管理层 | `none` | DocType: `Item Price`, `Item`, `Supplier`<br>Method: `search_documents` |
| `erpnext.buying.get_buying_settings` | `L0` | `agent_visible` | 采购、管理层、developer | `none` | DocType: `Buying Settings`<br>Method: `get_document` |
| `erpnext.buying.run_purchase_analysis` | `L0` | `agent_visible` | 采购、管理层 | `none` | DocType: `Purchase Order`, `Purchase Receipt`, `Supplier`, `Item`<br>Method: `run_report`<br>默认报表为 Purchase Analytics，filters 由报表工具规范化。 |
| `erpnext.buying.compare_supplier_quotations` | `L1` | `agent_visible` | 采购、管理层 | `none` | DocType: `Supplier Quotation`, `Supplier Quotation Item`<br>Method: `get_document` |
| `erpnext.buying.submit_document` | `L4` | `agent_visible` | 采购、仓管、管理层 | `submit_confirm` | DocType: `Material Request`, `Request for Quotation`, `Supplier Quotation`, `Purchase Order`, `Purchase Receipt`<br>Method: `submit_document` |

## 人工补充详情

本节展示已经人工补充业务约束的 ToolCall。未在本节展开的工具仍有基础契约，见后面的参数索引；后续可逐步补齐业务约束。

### `erpnext.search_documents`

| 项目 | 内容 |
|---|---|
| 用途 | L0：通用底层 DocType 查询，用于 Resolver、报表编排和内部状态检查。 |
| Allowed Roles | Runtime |
| Expose | `runtime_internal` |
| Confirm | `none` |
| Backend Mapping | DocType: `任意 DocType` |
| Repair | `validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `doctype`、`filters`、`fields`、`limit`、`order_by` |

Business Contract：

- 员工 Agent 不能直接请求该工具。
- 必须由 Runtime 构造 filters，禁止模型直接手写 Frappe filter DSL。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | DocType Resolver | `doctype` | 必须是 ERPNext 已存在 DocType。 | `resolve_entity`、`validate_before_execute` |
| `filters` | `object|array` | `no` | Runtime Builder | - | 必须由编排层生成，不能由模型直接拼。 | `validate_before_execute` |
| `fields` | `array` | `no` | Field Resolver | `field` | array_items_schema=true、字段必须存在于目标 DocType meta。 | `validate_before_execute` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | - | - | minimum=0 | - |
| `order_by` | `string` | `no` | - | - | - | - |

### `erpnext.search_items`

| 项目 | 内容 |
|---|---|
| 用途 | L0：检索标准化 ERPNext Item 主数据，返回候选和追问信息。 |
| Allowed Roles | 仓管、采购、项目经理、班组长、财务、资产管理员、管理层、系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Item` |
| Repair | `present_candidates`、`ask_clarification` |
| 审计重点 | `query`、`specs`、`item_group`、`enabled_only`、`limit` |

Business Contract：

- 检索结果不等于最终选择；低置信或多候选必须让用户确认。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `query` | `string` | `True` | 用户原话 | `item` | - | - |
| `specs` | `object` | `no` | Slot Extractor | - | - | - |
| `item_group` | `string` | `no` | Item Group Resolver | `item_group` | - | - |
| `enabled_only` | `boolean` | `no` | Runtime 默认值 | - | - | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=50 | - |

### `erpnext.count_documents`

| 项目 | 内容 |
|---|---|
| 用途 | L0：统计某个 DocType 的记录数量，供 Runtime 和 Resolver 使用。 |
| Allowed Roles | Runtime |
| Expose | `runtime_internal` |
| Confirm | `none` |
| Backend Mapping | DocType: `任意 DocType`<br>Method: `frappe.client.get_count` |
| Repair | `validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `doctype`、`filters` |

Business Contract：

- 员工 Agent 不直接手写 filters。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | DocType Resolver | `doctype` | 必须是 ERPNext 已存在 DocType。 | - |
| `filters` | `object|array` | `no` | Runtime Builder | - | 必须由编排层生成。 | - |

### `erpnext.get_document`

| 项目 | 内容 |
|---|---|
| 用途 | L0：按 DocType 和单据名读取一张 ERPNext 单据。 |
| Allowed Roles | Runtime |
| Expose | `runtime_internal` |
| Confirm | `none` |
| Backend Mapping | DocType: `任意 DocType` |
| Repair | `resolve_entity`、`validate_before_execute`、`permission_denied` |
| 审计重点 | `doctype`、`name` |

Business Contract：

- 用于 Runtime 读取上下文，员工 Agent 通常不直接请求。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | DocType Resolver | `doctype` | - | - |
| `name` | `string` | `True` | Document Resolver | `docname` | - | - |

### `erpnext.create_document`

| 项目 | 内容 |
|---|---|
| 用途 | L3：裸创建任意 DocType，开发和迁移时使用。 |
| Allowed Roles | developer |
| Expose | `developer_only` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `任意 DocType` |
| Repair | `permission_denied`、`erpnext_validation_error` |
| 审计重点 | `doctype`、`data` |

Business Contract：

- 员工 Agent 永不直接使用该工具。
- 如果业务需要新增单据，优先新增专用 ToolCall。
- 仅本地开发、迁移、调试或受控专家模式可以使用。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | Developer | `doctype` | 必须是 ERPNext 已存在 DocType。 | - |
| `data` | `object` | `True` | Developer | - | 完整 payload 必须进入审计日志。 | - |

### `erpnext.update_document`

| 项目 | 内容 |
|---|---|
| 用途 | L3：裸更新任意 DocType，开发、迁移和受控维护时使用。 |
| Allowed Roles | developer |
| Expose | `developer_only` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `任意 DocType` |
| Repair | `permission_denied`、`erpnext_validation_error` |
| 审计重点 | `doctype`、`name`、`data` |

Business Contract：

- 员工 Agent 永不直接使用该工具。
- 业务更新应优先通过专用 ToolCall 或业务 wrapper。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | Developer | `doctype` | 必须是 ERPNext 已存在 DocType。 | - |
| `name` | `string` | `True` | Developer | `docname` | 必须是目标 DocType 下已存在的单据名。 | - |
| `data` | `object` | `True` | Developer | - | 完整更新 payload 必须进入审计日志。 | - |

### `erpnext.delete_document`

| 项目 | 内容 |
|---|---|
| 用途 | L4：裸删除任意 DocType，开发和受控维护时使用。 |
| Allowed Roles | developer |
| Expose | `developer_only` |
| Confirm | `submit_confirm` |
| Backend Mapping | DocType: `任意 DocType` |
| Repair | `permission_denied`、`erpnext_validation_error` |
| 审计重点 | `doctype`、`name` |

Business Contract：

- 员工 Agent 永不直接使用该工具。
- 删除动作必须有明确确认和审计原因。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | Developer | `doctype` | 必须是 ERPNext 已存在 DocType。 | - |
| `name` | `string` | `True` | Developer | `docname` | 必须是目标 DocType 下已存在的单据名。 | - |

### `erpnext.document_exists`

| 项目 | 内容 |
|---|---|
| 用途 | L0：检查某张 ERPNext 单据是否存在。 |
| Allowed Roles | Runtime |
| Expose | `runtime_internal` |
| Confirm | `none` |
| Backend Mapping | DocType: `任意 DocType` |
| Repair | `resolve_entity`、`validate_before_execute` |
| 审计重点 | `doctype`、`name` |

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | DocType Resolver | `doctype` | - | - |
| `name` | `string` | `True` | Document Resolver | `docname` | - | - |

### `erpnext.resolve_link`

| 项目 | 内容 |
|---|---|
| 用途 | L0：为 Link 字段查找候选关联单据。 |
| Allowed Roles | Runtime |
| Expose | `runtime_internal` |
| Confirm | `none` |
| Backend Mapping | DocType: `任意 Link 目标 DocType` |
| Repair | `resolve_entity`、`present_candidates`、`validate_before_execute` |
| 审计重点 | `doctype`、`query`、`search_field`、`limit` |

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | Link Field Meta | `doctype` | - | - |
| `query` | `string` | `True` | 用户原话 / Runtime | - | 仅作为候选检索输入。 | - |
| `search_field` | `string` | `no` | Field Resolver | `field` | - | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=50 | - |

### `erpnext.validate_fields`

| 项目 | 内容 |
|---|---|
| 用途 | L0：执行 ToolCall 前校验字段名是否存在于目标 DocType。 |
| Allowed Roles | Runtime |
| Expose | `runtime_internal` |
| Confirm | `none` |
| Backend Mapping | DocType: `DocType Meta` |
| Repair | `validate_before_execute` |
| 审计重点 | `doctype`、`fields` |

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | DocType Resolver | `doctype` | - | - |
| `fields` | `array` | `True` | Runtime Builder | `field` | array_items_schema=true | - |

### `erpnext.get_doctype_schema`

| 项目 | 内容 |
|---|---|
| 用途 | L0：读取 ERPNext DocType 元数据和字段结构。 |
| Allowed Roles | Runtime |
| Expose | `runtime_internal` |
| Confirm | `none` |
| Backend Mapping | DocType: `DocType Meta` |
| Repair | `resolve_entity`、`permission_denied` |
| 审计重点 | `doctype` |

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | DocType Resolver | `doctype` | - | - |

### `erpnext.submit_document`

| 项目 | 内容 |
|---|---|
| 用途 | L4：通过 ERPNext 服务端规则提交一张可提交单据。 |
| Allowed Roles | Runtime |
| Expose | `runtime_internal` |
| Confirm | `submit_confirm` |
| Backend Mapping | DocType: `任意可提交 DocType`<br>Method: `agent_bridge.api.submit_document` |
| Repair | `validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `doctype`、`name`、`confirmation` |

Business Contract：

- 员工 Agent 不直接调用通用提交；应通过模块专用 submit 工具或业务流程节点。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | - | `doctype` | - | - |
| `name` | `string` | `True` | - | `docname` | - | - |
| `confirmation` | `object` | `conditional` | Confirmation Policy | - | - | - |

### `erpnext.cancel_document`

| 项目 | 内容 |
|---|---|
| 用途 | L4：通过 ERPNext 服务端规则取消一张已提交单据。 |
| Allowed Roles | Runtime |
| Expose | `runtime_internal` |
| Confirm | `submit_confirm` |
| Backend Mapping | DocType: `任意可取消 DocType`<br>Method: `agent_bridge.api.cancel_document` |
| Repair | `validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `doctype`、`name`、`confirmation` |

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | - | `doctype` | - | - |
| `name` | `string` | `True` | - | `docname` | - | - |
| `confirmation` | `object` | `conditional` | Confirmation Policy | - | - | - |

### `erpnext.apply_workflow`

| 项目 | 内容 |
|---|---|
| 用途 | L4：对某张 ERPNext 单据执行工作流动作。 |
| Allowed Roles | Runtime |
| Expose | `runtime_internal` |
| Confirm | `submit_confirm` |
| Backend Mapping | Method: `frappe.model.workflow.apply_workflow` |
| Repair | `validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `doctype`、`name`、`action` |

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | - | `doctype` | - | - |
| `name` | `string` | `True` | - | `docname` | - | - |
| `action` | `string` | `True` | Workflow Action Resolver | - | 必须来自 erpnext.get_workflow_actions 返回的可执行动作。 | - |

### `erpnext.users.list_users`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 ERPNext User 安全身份和状态字段。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `User` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `query`、`enabled`、`user_type`、`role_profile_name`、`limit` |

Business Contract：

- 只返回用户身份、启用状态、用户类型、角色配置和登录活动等安全摘要字段。
- 查询结果不得直接作为新增、停用或改权限依据；写操作必须重新展示并确认目标用户。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `query` | `string` | `no` | 用户原话 | `user` | 仅作为 User.full_name 模糊检索输入。 | - |
| `enabled` | `boolean` | `no` | 用户筛选条件 | - | - | - |
| `user_type` | `string` | `no` | 用户筛选条件 | - | - | - |
| `role_profile_name` | `string` | `no` | Role Profile Resolver | `role_profile` | 如填写，必须是已存在的 ERPNext Role Profile.name。 | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | Runtime 分页 | - | minimum=0 | - |

### `erpnext.users.get_user_access_summary`

| 项目 | 内容 |
|---|---|
| 用途 | L0：读取单个用户的启用状态、角色、角色配置和直接 User Permission 摘要。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `User`, `User Permission` |
| Repair | `resolve_entity`、`ask_clarification`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `user`、`include_permissions` |

Business Contract：

- 只读访问摘要；不会创建、删除、启停用户或分配角色。
- 直接 User Permission 只代表限制/默认维度之一，不等同完整运行时权限判定。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `user` | `string` | `True` | User Resolver | `user` | 必须是已存在的 ERPNext User.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `include_permissions` | `boolean` | `no` | Runtime 默认值 / 用户选择 | - | - | - |

### `erpnext.users.list_roles`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 ERPNext Role 主数据候选。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Role` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `query`、`disabled`、`desk_access`、`limit` |

Business Contract：

- 查询结果只用于候选展示；角色分配必须使用 erpnext.users.assign_roles 并获得 admin_confirm。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `query` | `string` | `no` | 用户原话 | `role` | 仅作为 Role.role_name 模糊检索输入。 | - |
| `disabled` | `boolean` | `no` | 用户筛选条件 | - | - | - |
| `desk_access` | `boolean` | `no` | 用户筛选条件 | - | - | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | Runtime 分页 | - | minimum=0 | - |

### `erpnext.users.list_role_profiles`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 ERPNext Role Profile 主数据候选。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Role Profile` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `query`、`limit` |

Business Contract：

- 查询结果只用于候选展示；将角色配置写入 User 必须通过创建/更新用户的管理员确认流程。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `query` | `string` | `no` | 用户原话 | `role_profile` | 仅作为 Role Profile 候选检索输入。 | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | Runtime 分页 | - | minimum=0 | - |

### `erpnext.users.preview_role_profile_roles`

| 项目 | 内容 |
|---|---|
| 用途 | L0：预览一个 Role Profile 会展开出的角色列表，不写入 User。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Role Profile`, `Role` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `role_profile` |

Business Contract：

- 仅预览角色配置包含的角色；不会分配给任何用户。
- 角色配置预览结果用于后续人工确认，不能自动触发 assign_roles。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `role_profile` | `string` | `True` | Role Profile Resolver | `role_profile` | 必须是已存在的 ERPNext Role Profile.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |

### `erpnext.users.list_user_permissions`

| 项目 | 内容 |
|---|---|
| 用途 | L0：按用户、允许 DocType、允许值或适用 DocType 查询 User Permission 行。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `User Permission` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `user`、`allow`、`for_value`、`applicable_for`、`limit` |

Business Contract：

- 只读 User Permission 行；新增或删除必须使用对应 admin_confirm 工具。
- 默认口径：for_value 的目标 DocType 必须由 allow 字段决定；解析时必须先解析 allow，再用对应 DocType resolver 解析 for_value。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `user` | `string` | `no` | User Resolver | `user` | 如填写，必须是已存在的 ERPNext User.name。 | - |
| `allow` | `string` | `no` | DocType Resolver | `doctype` | 如填写，必须是 User Permission.allow 支持的 DocType。 | - |
| `for_value` | `string` | `no` | Document Resolver | `docname` | 如填写，必须是 allow 对应 DocType 下已存在的单据名。 | - |
| `applicable_for` | `string` | `no` | DocType Resolver | `doctype` | 如填写，必须是已存在的 ERPNext DocType.name。 | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | Runtime 分页 | - | minimum=0 | - |

### `erpnext.users.list_shared_documents`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 DocShare 共享文档行。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `DocShare` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `user`、`share_doctype`、`share_name`、`limit` |

Business Contract：

- 只读共享记录，不创建或移除共享。
- 默认口径：DocShare 使用 Frappe 标准 read/write/share/submit/everyone 标志；write、share、submit 必须进入管理员确认摘要。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `user` | `string` | `no` | User Resolver | `user` | 如填写，必须是已存在的 ERPNext User.name。 | - |
| `share_doctype` | `string` | `no` | DocType Resolver | `doctype` | 如填写，必须是已存在的 ERPNext DocType.name。 | - |
| `share_name` | `string` | `no` | Document Resolver | `docname` | 如填写，必须是 share_doctype 下已存在的单据名。 | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | Runtime 分页 | - | minimum=0 | - |

### `erpnext.users.list_access_logs`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 Access Log 审计记录。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Access Log` |
| Repair | `resolve_entity`、`ask_clarification`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `user`、`limit` |

Business Contract：

- 只读访问日志，不修改用户或权限。
- 日志保留期和字段完整性取决于当前站点配置。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `user` | `string` | `no` | User Resolver | `user` | 如填写，必须是已存在的 ERPNext User.name。 | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | Runtime 分页 | - | minimum=0 | - |

### `erpnext.users.list_activity_logs`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 Activity Log 审计记录。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Activity Log` |
| Repair | `resolve_entity`、`ask_clarification`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `user`、`subject`、`limit` |

Business Contract：

- 只读活动日志，不修改用户或权限。
- subject 仅作为日志主题筛选，不应当作权限判断依据。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `user` | `string` | `no` | User Resolver | `user` | 如填写，必须是已存在的 ERPNext User.name。 | - |
| `subject` | `string` | `no` | 用户筛选条件 | - | - | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | Runtime 分页 | - | minimum=0 | - |

### `erpnext.users.get_permission_metadata`

| 项目 | 内容 |
|---|---|
| 用途 | L0：读取某个 DocType 的 DocPerm/Custom DocPerm 风格权限元数据。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `DocType Meta`<br>Method: `ERPNextClient.get_doctype_schema` |
| Repair | `resolve_entity`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `doctype` |

Business Contract：

- 只读权限元数据；不会修改 DocPerm 或 Custom DocPerm。
- 权限元数据不等同服务器运行时最终判定，必要时使用 check_server_permission。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | DocType Resolver | `doctype` | 必须是已存在的 ERPNext DocType.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |

### `erpnext.users.preview_effective_permissions`

| 项目 | 内容 |
|---|---|
| 用途 | L0：基于用户角色、DocType 权限元数据和直接 User Permission 预览用户权限，不写入 ERPNext。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `User`, `DocType Meta`, `User Permission` |
| Repair | `resolve_entity`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `user`、`doctype`、`include_user_permissions` |

Business Contract：

- 这是元数据层预览，不是完整服务器运行时权限判定。
- 预览结果不能自动触发角色分配、用户权限增删或 DocPerm 修改。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `user` | `string` | `True` | User Resolver | `user` | 必须是已存在的 ERPNext User.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `doctype` | `string` | `True` | DocType Resolver | `doctype` | 必须是已存在的 ERPNext DocType.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `include_user_permissions` | `boolean` | `no` | Runtime 默认值 / 用户选择 | - | - | - |

### `erpnext.users.check_server_permission`

| 项目 | 内容 |
|---|---|
| 用途 | L0：调用后端权限检查能力，对比服务器运行时权限和元数据预览。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `User`, `DocType Meta`<br>Method: `agent_bridge.api.check_user_permission` |
| Repair | `resolve_entity`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `user`、`doctype`、`docname`、`action`、`debug` |

Business Contract：

- 只检查权限，不修改任何用户、角色或共享记录。
- docname 如填写，必须与 doctype 一起解析，不能脱离 DocType 单独猜测。
- 默认口径：权限检查必须以当前 API 用户身份执行，不允许用系统管理员身份绕过；返回结果应包含执行用户和 Frappe 版本调试信息。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `user` | `string` | `True` | User Resolver | `user` | 必须是已存在的 ERPNext User.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `doctype` | `string` | `True` | DocType Resolver | `doctype` | 必须是已存在的 ERPNext DocType.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `docname` | `string` | `no` | Document Resolver | `docname` | 如填写，必须是 doctype 下已存在的单据名。 | - |
| `action` | `enum` | `True` | 权限动作枚举 | - | 只能使用 schema 枚举中的 Frappe 权限动作。 | - |
| `debug` | `boolean` | `no` | Runtime / 管理员选择 | - | - | - |

### `erpnext.users.preview_permission_policy_change`

| 项目 | 内容 |
|---|---|
| 用途 | L5_ADMIN 预览：模拟 DocPerm 风格权限策略变更的前后差异，不写入 ERPNext。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `DocType Meta` |
| Repair | `resolve_entity`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `doctype`、`changes` |

Business Contract：

- 该工具只做预览，不创建、更新或删除 DocPerm/Custom DocPerm。
- changes 中涉及的 role、permlevel、match.name 和权限位必须来自明确输入或现有元数据。
- 真正修改权限策略需要单独的 L5_ADMIN 写工具和 admin_confirm；当前 schema 未提供写工具。
- 默认口径：运行期权限修改优先写 Custom DocPerm；变更后刷新权限缓存，迁移/fixtures 由开发流程处理，不由 Agent 自动执行。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | DocType Resolver | `doctype` | 必须是已存在的 ERPNext DocType.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `changes` | `array` | `True` | 权限策略预览表单编排 | `role` | array_items_schema=true、数组至少 1 行。、operation 只能是 add、update、remove。、role 必须解析为已存在的 ERPNext Role.name。、remove/update 的 match.name 如填写，必须来自读取到的现有权限行。 | `resolve_entity`、`ask_clarification`、`validate_before_execute` |

### `erpnext.users.create_user_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L5_ADMIN：创建 User 主数据草稿式记录，默认禁用且不发送欢迎邮件。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `admin_confirm` |
| Backend Mapping | DocType: `User`, `Role`<br>Method: `ERPNextClient.create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `email`、`first_name`、`last_name`、`user_type`、`role_profile_name`、`roles`、`enabled`、`send_welcome_email`、`confirmation` |

Business Contract：

- 创建前必须展示邮箱、姓名、用户类型、是否启用、是否发送欢迎邮件、角色配置和角色列表。
- 默认应保持 enabled=false、send_welcome_email=false，除非管理员明确确认。
- roles 中每个角色必须来自 Role Resolver；role_profile_name 必须来自 Role Profile Resolver。
- 默认口径：Agent 不设置明文初始密码；SSO、欢迎邮件和员工关联按站点安全策略执行，Employee 关联必须 resolver 命中并经管理员确认。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `email` | `string` | `True` | 用户确认邮箱 | - | 通常作为 ERPNext User.name；必须进入管理员确认摘要。 | - |
| `first_name` | `string` | `True` | 用户确认姓名 | - | - | - |
| `last_name` | `string` | `no` | 用户确认姓名 | - | - | - |
| `user_type` | `string` | `no` | 用户选择 / Runtime 默认值 | - | - | - |
| `role_profile_name` | `string` | `no` | Role Profile Resolver | `role_profile` | 如填写，必须是已存在的 ERPNext Role Profile.name。 | - |
| `roles` | `array` | `no` | Role Resolver | `role` | array_items_schema=true、每个元素必须是已存在的 ERPNext Role.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `enabled` | `boolean` | `no` | 管理员确认 | - | 默认 false；启用新用户必须明确说明。 | - |
| `send_welcome_email` | `boolean` | `no` | 管理员确认 | - | 默认 false；发送欢迎邮件必须明确说明。 | - |
| `confirmation` | `object` | `True` | Admin Confirmation Policy | - | - | - |

### `erpnext.users.set_user_enabled`

| 项目 | 内容 |
|---|---|
| 用途 | L5_ADMIN：启用或停用 ERPNext User。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `admin_confirm` |
| Backend Mapping | DocType: `User`<br>Method: `ERPNextClient.update_document` |
| Repair | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `user`、`enabled`、`confirmation` |

Business Contract：

- 执行前必须展示目标用户、当前状态和目标状态。
- 停用系统集成账号、管理员账号或当前会话用户必须升级人工复核。
- 默认口径：禁止通过 ToolCall 启停 Administrator、Guest、集成用户和 API 用户；这类账号必须由系统管理员在后台人工处理。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `user` | `string` | `True` | User Resolver | `user` | 必须是已存在的 ERPNext User.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `enabled` | `boolean` | `True` | 管理员确认 | - | - | - |
| `confirmation` | `object` | `True` | Admin Confirmation Policy | - | - | - |

### `erpnext.users.assign_roles`

| 项目 | 内容 |
|---|---|
| 用途 | L5_ADMIN：对一个 User 执行角色 replace、add 或 remove。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `admin_confirm` |
| Backend Mapping | DocType: `User`, `Role`<br>Method: `ERPNextClient.update_document` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `user`、`mode`、`roles`、`confirmation` |

Business Contract：

- 执行前必须展示目标用户、操作模式、当前角色、目标角色和差异。
- replace 模式会覆盖用户现有角色，必须特别提示。
- roles 中每个角色必须是已存在 Role.name，禁止凭空创造角色。
- 默认口径：System Manager、Administrator 等高权限角色授权必须 admin_confirm，并在确认摘要中单独列出高权限风险。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `user` | `string` | `True` | User Resolver | `user` | 必须是已存在的 ERPNext User.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `mode` | `enum` | `True` | 管理员选择 | - | 只能是 replace、add、remove。 | - |
| `roles` | `array` | `True` | Role Resolver | `role` | array_items_schema=true、数组至少 1 行。、每个元素必须是已存在的 ERPNext Role.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `confirmation` | `object` | `True` | Admin Confirmation Policy | - | - | - |

### `erpnext.users.create_user_permission`

| 项目 | 内容 |
|---|---|
| 用途 | L5_ADMIN：创建 User Permission 行。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `admin_confirm` |
| Backend Mapping | DocType: `User Permission`, `User`<br>Method: `ERPNextClient.create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `user`、`allow`、`for_value`、`applicable_for`、`is_default`、`hide_descendants`、`confirmation` |

Business Contract：

- 执行前必须展示目标用户、允许 DocType、允许值、适用 DocType、是否默认和是否隐藏子级。
- allow 与 for_value 必须一起解析；for_value 不能脱离 allow 单独猜测。
- 默认口径：User Permission 先按 allow 解析层级语义；is_default 冲突必须前置查询，hide_descendants 仅在目标 DocType 支持树结构时可用。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `user` | `string` | `True` | User Resolver | `user` | 必须是已存在的 ERPNext User.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `allow` | `string` | `True` | DocType Resolver | `doctype` | 必须是 User Permission.allow 支持的 DocType。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `for_value` | `string` | `True` | Document Resolver | `docname` | 必须是 allow 对应 DocType 下已存在的单据名。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `applicable_for` | `string` | `no` | DocType Resolver | `doctype` | 如填写，必须是已存在的 ERPNext DocType.name。 | - |
| `is_default` | `boolean` | `no` | 管理员确认 | - | - | - |
| `hide_descendants` | `boolean` | `no` | 管理员确认 | - | - | - |
| `confirmation` | `object` | `True` | Admin Confirmation Policy | - | - | - |

### `erpnext.users.delete_user_permission`

| 项目 | 内容 |
|---|---|
| 用途 | L5_ADMIN：按名称删除 User Permission 行。 |
| Allowed Roles | 系统管理员 |
| Expose | `agent_visible` |
| Confirm | `admin_confirm` |
| Backend Mapping | DocType: `User Permission`<br>Method: `ERPNextClient.delete_document` |
| Repair | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `name`、`confirmation` |

Business Contract：

- 删除前必须读取并展示 User Permission 行的 user、allow、for_value、applicable_for 等字段。
- 删除动作不可仅凭用户描述执行，必须确认精确 User Permission.name。
- 默认口径：删除 User Permission 后必须刷新权限缓存并记录审计；无法自动刷新时返回 user_message 提醒管理员重新登录或清缓存。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `name` | `string` | `True` | Document Resolver | `docname` | 必须是已存在的 User Permission.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `confirmation` | `object` | `True` | Admin Confirmation Policy | - | - | - |

### `erpnext.accounting.search_accounts`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询会计科目主数据，用于报表筛选、凭证草稿编排和科目解析。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Account`<br>只读 search_documents；默认按 lft asc 返回科目树。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `company`、`account_type`、`filters`、`limit` |

Business Contract：

- 仅用于读取 Account，不创建或修改科目。
- company 必须解析成 ERPNext Company.name 全称；不能把用户简称直接写入 ToolCall。
- filters、fields、order_by 必须由 Runtime 生成或校验，禁止模型直接拼接未校验的 Frappe filter DSL。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `company` | `string` | `no` | Company Resolver / Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `account_type` | `string` | `no` | 用户选择 / Runtime 枚举 | - | 用于缩小 Account.account_type，不应作为科目主键。 | - |
| `filters` | `object|array` | `no` | Runtime Builder | - | 必须由编排层生成或白名单校验。 | `validate_before_execute` |
| `fields` | `array` | `no` | Runtime 默认 / Field Resolver | `field` | array_items_schema=true、字段必须存在于 Account meta。 | `validate_before_execute` |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100、默认由 Runtime 控制，避免一次返回过多科目。 | - |
| `offset` | `integer` | `no` | - | - | minimum=0 | - |
| `order_by` | `string` | `no` | - | - | - | - |

### `erpnext.accounting.search_cost_centers`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询成本中心主数据，用于报表筛选、预算和单据草稿编排。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Cost Center`<br>只读 search_documents；默认按 lft asc 返回成本中心树。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `company`、`filters`、`limit` |

Business Contract：

- 仅用于读取 Cost Center，不创建或修改成本中心。
- company 和 cost_center 相关筛选必须先解析，不允许使用简称直接作为 ERPNext 主键。
- filters、fields、order_by 必须由 Runtime 生成或校验。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `company` | `string` | `no` | Company Resolver / Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `filters` | `object|array` | `no` | Runtime Builder | - | 如果包含 name/parent_cost_center/company，必须来自 resolver 或已校验上下文。 | `validate_before_execute`、`resolve_entity` |
| `fields` | `array` | `no` | Runtime 默认 / Field Resolver | `field` | array_items_schema=true、字段必须存在于 Cost Center meta。 | `validate_before_execute` |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | - | - | minimum=0 | - |
| `order_by` | `string` | `no` | - | - | - | - |

### `erpnext.accounting.search_budgets`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询预算单据，用于预算状态核对和预算草稿更新前定位。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Budget` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `company`、`fiscal_year`、`filters`、`limit` |

Business Contract：

- 仅用于读取 Budget，不创建、不更新、不提交预算。
- company、fiscal_year 必须解析为 ERPNext 主数据全称。
- filters、fields、order_by 必须由 Runtime 生成或校验。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `company` | `string` | `no` | Company Resolver / Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `fiscal_year` | `string` | `no` | Fiscal Year Resolver / 用户选择 | `fiscal_year` | 必须是 ERPNext Fiscal Year.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `filters` | `object|array` | `no` | Runtime Builder | - | 预算维度筛选必须由编排层生成或白名单校验。 | `validate_before_execute` |
| `fields` | `array` | `no` | Runtime 默认 / Field Resolver | `field` | array_items_schema=true、字段必须存在于 Budget meta。 | `validate_before_execute` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | - | - | minimum=0 | - |
| `order_by` | `string` | `no` | - | - | - | - |

### `erpnext.accounting.search_fiscal_years`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询会计年度主数据，用于报表、预算和期间类单据编排。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Fiscal Year` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `year`、`disabled`、`filters`、`limit` |

Business Contract：

- 仅用于读取 Fiscal Year，不创建或修改会计年度。
- 用户说本年、上年、本会计年度时，必须由日期/会计年度 resolver 转换为 Fiscal Year.name。
- filters、fields、order_by 必须由 Runtime 生成或校验。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `year` | `string` | `no` | Fiscal Year Resolver / Date Resolver | `fiscal_year` | 可作为 Fiscal Year 检索输入，不能凭空编造会计年度名称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `disabled` | `boolean` | `no` | 用户选择 / Runtime 默认 | - | - | - |
| `filters` | `object|array` | `no` | Runtime Builder | - | 必须由编排层生成或白名单校验。 | `validate_before_execute` |
| `fields` | `array` | `no` | Runtime 默认 / Field Resolver | `field` | array_items_schema=true、字段必须存在于 Fiscal Year meta。 | `validate_before_execute` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | - | - | minimum=0 | - |
| `order_by` | `string` | `no` | - | - | - | - |

### `erpnext.accounting.search_accounting_periods`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询会计期间，用于报表日期范围和关账草稿编排前检查。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Accounting Period` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `company`、`from_date`、`to_date`、`filters`、`limit` |

Business Contract：

- 仅用于读取 Accounting Period，不创建或修改期间。
- 日期范围必须是明确 ISO 日期，不接受本月左右、近期等模糊表达直接入参。
- company 必须来自 resolver 或 Runtime 上下文。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `company` | `string` | `no` | Company Resolver / Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `from_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。 | `ask_clarification`、`inject_context` |
| `to_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。、不得早于 from_date。 | `ask_clarification`、`validate_before_execute` |
| `filters` | `object|array` | `no` | Runtime Builder | - | 必须由编排层生成或白名单校验。 | `validate_before_execute` |
| `fields` | `array` | `no` | - | - | array_items_schema=true | - |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | - | - | minimum=0 | - |
| `order_by` | `string` | `no` | - | - | - | - |

### `erpnext.accounting.search_payment_terms`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询付款条件或付款条件模板，用于发票草稿编排。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Payment Term`, `Payment Terms Template` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `doctype`、`query`、`filters`、`limit` |

Business Contract：

- 仅用于读取付款条件主数据，不创建或修改付款条件。
- doctype 只能是 Payment Term 或 Payment Terms Template。
- query 只能作为检索输入；命中多个模板时必须展示候选。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `enum` | `no` | Runtime 默认 / 用户选择 | - | 默认 Payment Term；只能使用 schema 枚举值。 | `validate_before_execute` |
| `query` | `string` | `no` | 用户原话 | `payment_terms` | 仅作为检索输入，不能直接当成 ERPNext 主键。 | `resolve_entity`、`present_candidates` |
| `filters` | `object|array` | `no` | Runtime Builder | - | 必须由编排层生成或白名单校验。 | `validate_before_execute` |
| `fields` | `array` | `no` | Runtime 默认 / Field Resolver | `field` | array_items_schema=true、字段必须存在于目标 DocType meta。 | `validate_before_execute` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | - | - | minimum=0 | - |
| `order_by` | `string` | `no` | - | - | - | - |

### `erpnext.accounting.search_tax_templates`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询销售/采购税费模板，用于发票税行准备。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Sales Taxes and Charges Template`, `Purchase Taxes and Charges Template` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `template_type`、`query`、`company`、`tax_category`、`disabled`、`limit` |

Business Contract：

- 仅用于读取税费模板，不创建或修改税费模板。
- template_type 必须与目标发票类型一致；销售发票使用 sales，采购发票使用 purchase。
- company 必须解析成 ERPNext Company.name 全称。
- 命中多个税费模板时必须展示候选，不允许模型自行选择。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `template_type` | `enum` | `no` | 发票类型 / Runtime 推断 | - | 只能使用 schema 枚举值。 | `ask_clarification`、`validate_before_execute` |
| `query` | `string` | `no` | 用户原话 | `tax_template` | 仅作为检索输入，不能直接当成税费模板主键。 | `resolve_entity`、`present_candidates` |
| `company` | `string` | `no` | Company Resolver / Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `tax_category` | `string` | `no` | Tax Category Resolver / 用户选择 | `tax_category` | 如作为筛选条件，必须来自 ERPNext 主数据或已校验上下文。 | `resolve_entity`、`present_candidates` |
| `disabled` | `boolean` | `no` | 用户选择 / Runtime 默认 | - | - | - |
| `filters` | `object|array` | `no` | Runtime Builder | - | 必须由编排层生成或白名单校验。 | `validate_before_execute` |
| `fields` | `array` | `no` | - | - | array_items_schema=true | - |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | - | - | minimum=0 | - |
| `order_by` | `string` | `no` | - | - | - | - |

### `erpnext.accounting.get_report_filters`

| 项目 | 内容 |
|---|---|
| 用途 | L0：读取标准财务报表的过滤器契约，不运行报表。 |
| Allowed Roles | 财务、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Report`<br>Report: `General Ledger`, `Accounts Receivable`, `Accounts Payable`, `Trial Balance`, `Balance Sheet`, `Profit and Loss Statement`, `Cash Flow` |
| Repair | `ask_clarification`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `report_name` |

Business Contract：

- 只读取报表过滤器契约，不运行报表、不读取财务数据行。
- report_name 必须使用 schema 枚举值。
- 用于在运行报表前收集 company、date、fiscal_year、account、party 等 resolver 结果。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `report_name` | `enum` | `True` | 用户选择 / Runtime 枚举 | - | 只能使用 schema 枚举值。 | `ask_clarification`、`validate_before_execute` |

### `erpnext.accounting.general_ledger`

| 项目 | 内容 |
|---|---|
| 用途 | L0：运行 General Ledger 只读报表。 |
| Allowed Roles | 财务、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | Report: `General Ledger`<br>run_report 只读；必填 company。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `company`、`from_date`、`to_date`、`account`、`party_type`、`party` |

Business Contract：

- 只读运行总账报表，不创建、不修改、不提交任何财务单据。
- company 必填且必须由 Company Resolver 或 Runtime Context 提供。
- from_date/to_date 必须是明确 ISO 日期；to_date 不得早于 from_date。
- account、party 必须解析为 ERPNext 主键；命中多个候选时必须展示候选。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `company` | `string` | `True` | Company Resolver / Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `from_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。 | `ask_clarification`、`inject_context` |
| `to_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。、不得早于 from_date。 | `ask_clarification`、`validate_before_execute` |
| `account` | `string` | `no` | Account Resolver | `account` | 必须是 ERPNext Account.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `party_type` | `string` | `no` | 用户选择 / Runtime 推断 | - | 使用 ERPNext 支持的 party_type；当前 schema 未枚举，执行前需校验。 | `ask_clarification`、`validate_before_execute` |
| `party` | `string` | `no` | Party Resolver | `party` | 必须与 party_type 匹配，解析为 Customer/Supplier 等 ERPNext 主键。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `filters` | `object` | `no` | Runtime Builder | - | 可包含 voucher_no、cost_center、project 等已校验筛选；禁止模型直接拼 filter DSL。、如果包含 cost_center，必须来自 Cost Center Resolver。 | `validate_before_execute`、`resolve_entity` |

### `erpnext.accounting.accounts_receivable`

| 项目 | 内容 |
|---|---|
| 用途 | L0：运行 Accounts Receivable 只读报表。 |
| Allowed Roles | 财务、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | Report: `Accounts Receivable`<br>run_report 只读；必填 company。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `company`、`from_date`、`to_date`、`party` |

Business Contract：

- 只读运行应收账款报表，不创建、不修改、不提交任何财务单据。
- company 必填且必须由 Company Resolver 或 Runtime Context 提供。
- party 如填写，必须解析为 ERPNext Customer.name。
- 默认口径：ToolCall 统一接收 from_date/to_date；应收报表执行时用 to_date 映射 ERPNext report_date，并把 from_date 作为账龄/期间过滤上下文。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `company` | `string` | `True` | Company Resolver / Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `from_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期；日期口径需与报表 filter spec 对齐。 | `ask_clarification`、`validate_before_execute` |
| `to_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期；日期口径需与报表 filter spec 对齐。 | `ask_clarification`、`validate_before_execute` |
| `party` | `string` | `no` | Customer Resolver | `customer` | 必须是 ERPNext Customer.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `filters` | `object` | `no` | Runtime Builder | - | 可包含 customer、customer_group、payment_terms_template 等已校验筛选。、禁止模型直接拼 filter DSL。 | `validate_before_execute`、`resolve_entity` |

### `erpnext.accounting.accounts_payable`

| 项目 | 内容 |
|---|---|
| 用途 | L0：运行 Accounts Payable 只读报表。 |
| Allowed Roles | 财务、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | Report: `Accounts Payable`<br>run_report 只读；必填 company。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `company`、`from_date`、`to_date`、`party` |

Business Contract：

- 只读运行应付账款报表，不创建、不修改、不提交任何财务单据。
- company 必填且必须由 Company Resolver 或 Runtime Context 提供。
- party 如填写，必须解析为 ERPNext Supplier.name。
- 默认口径：ToolCall 统一接收 from_date/to_date；应付报表执行时用 to_date 映射 ERPNext report_date，并把 from_date 作为账龄/期间过滤上下文。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `company` | `string` | `True` | Company Resolver / Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `from_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期；日期口径需与报表 filter spec 对齐。 | `ask_clarification`、`validate_before_execute` |
| `to_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期；日期口径需与报表 filter spec 对齐。 | `ask_clarification`、`validate_before_execute` |
| `party` | `string` | `no` | Supplier Resolver | `supplier` | 必须是 ERPNext Supplier.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `filters` | `object` | `no` | Runtime Builder | - | 可包含 supplier、supplier_group、payment_terms_template 等已校验筛选。、禁止模型直接拼 filter DSL。 | `validate_before_execute`、`resolve_entity` |

### `erpnext.accounting.financial_report`

| 项目 | 内容 |
|---|---|
| 用途 | L0：运行 Trial Balance、Balance Sheet、Profit and Loss Statement 或 Cash Flow 只读报表。 |
| Allowed Roles | 财务、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | Report: `Trial Balance`, `Balance Sheet`, `Profit and Loss Statement`, `Cash Flow`<br>run_report 只读；必填 company。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `report_name`、`company`、`from_date`、`to_date`、`fiscal_year` |

Business Contract：

- 只读运行财务报表，不创建、不修改、不提交任何财务单据。
- company 必填且必须由 Company Resolver 或 Runtime Context 提供。
- report_name 必须使用 schema 枚举值。
- fiscal_year、日期和 filters 中的 cost_center 必须来自 resolver 或已校验上下文。
- 默认口径：财务报表 ToolCall 统一接收 from_date/to_date，报表适配层负责映射为 ERPNext 所需的 period_start_date/period_end_date、from_fiscal_year/to_fiscal_year 或 filters 字段。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `report_name` | `enum` | `True` | 用户选择 / Runtime 枚举 | - | 只能使用 schema 枚举值。 | `ask_clarification`、`validate_before_execute` |
| `company` | `string` | `True` | Company Resolver / Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `from_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期；具体映射需与报表 filter spec 对齐。 | `ask_clarification`、`validate_before_execute` |
| `to_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期；具体映射需与报表 filter spec 对齐。、不得早于 from_date。 | `ask_clarification`、`validate_before_execute` |
| `fiscal_year` | `string` | `no` | Fiscal Year Resolver / Date Resolver | `fiscal_year` | 必须是 ERPNext Fiscal Year.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `filters` | `object` | `no` | Runtime Builder | - | 可包含 finance_book、cost_center、project、periodicity 等已校验筛选。、如果包含 cost_center，必须来自 Cost Center Resolver。、禁止模型直接拼 filter DSL。 | `validate_before_execute`、`resolve_entity` |

### `erpnext.accounting.create_journal_entry_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Journal Entry 草稿，不提交。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Journal Entry`, `Journal Entry Account` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `data` |

Business Contract：

- 只创建 docstatus=0 的草稿；提交必须另行使用 submit_financial_document 并经过 financial_confirm。
- 创建前必须让用户确认凭证日期、公司、分录科目、借贷方向、金额和业务说明。
- data 中的 company、posting_date、accounts.account、accounts.cost_center、party 必须由 resolver 或已校验上下文生成。
- 默认口径：执行前必须做借贷平衡和基础科目状态预检；冻结期间、禁用科目和期间锁定最终由 ERPNext 服务端再次拦截。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | 财务凭证表单编排 | - | 必须是 Journal Entry draft payload；docstatus 会被服务端强制为 0。、data.company 必须来自 Company Resolver。、data.posting_date 必须来自 Date Resolver。、accounts[].account 必须来自 Account Resolver。、accounts[].cost_center 必须来自 Cost Center Resolver。、accounts[].party 必须来自 Party Resolver 并与 party_type 匹配。、完整 payload 必须进入审计日志。 | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`erpnext_validation_error` |

### `erpnext.accounting.create_payment_entry_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Payment Entry 草稿，不提交。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Payment Entry`, `Payment Entry Reference` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `data` |

Business Contract：

- 只创建 docstatus=0 的草稿；提交必须另行使用 submit_financial_document 并经过 financial_confirm。
- 创建前必须确认收/付款类型、公司、往来方、金额、付款账户、收款账户、引用发票和分配金额。
- data 中的 company、party、posting_date、paid_from、paid_to、references[].reference_name 必须由 resolver 或已校验上下文生成。
- 建议先使用 prepare_payment_allocation 生成发票分配候选。
- 制度配置项：汇兑损益、手续费、差额账户和跨币种付款规则必须来自公司财务制度或 ERPNext Payment Entry 配置，Agent 不得自行推断。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | 付款分配结果 + 财务表单编排 | - | 必须是 Payment Entry draft payload；docstatus 会被服务端强制为 0。、data.company 必须来自 Company Resolver。、data.posting_date 必须来自 Date Resolver。、data.party 必须来自 Customer/Supplier Resolver 并与 party_type 匹配。、data.paid_from/data.paid_to 必须来自 Account Resolver 或 Bank Account Resolver。、references[].reference_name 必须来自 Invoice Resolver。、完整 payload 必须进入审计日志。 | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`erpnext_validation_error` |

### `erpnext.accounting.create_sales_invoice_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Sales Invoice 草稿，不提交。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Sales Invoice`, `Sales Invoice Item`, `Sales Taxes and Charges` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `data` |

Business Contract：

- 只创建 docstatus=0 的草稿；提交必须另行使用 submit_financial_document 并经过 financial_confirm。
- 创建前必须确认客户、公司、日期、明细、数量、价格、税费模板或税行、收入科目和成本中心。
- data.customer 必须来自 Customer Resolver；data.company、posting_date、due_date、items[].income_account、items[].cost_center 必须由对应 resolver 或已校验上下文生成。
- 制度配置项：价格来源、税费计算、收入确认和库存影响规则以公司财务制度、ERPNext 税费模板和服务端校验为准，Agent 只能使用解析出的模板或用户确认值。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | 销售发票表单编排 | - | 必须是 Sales Invoice draft payload；docstatus 会被服务端强制为 0。、data.customer 必须来自 Customer Resolver。、data.company 必须来自 Company Resolver。、data.posting_date/data.due_date 必须来自 Date Resolver。、items[].income_account 必须来自 Account Resolver。、items[].cost_center 必须来自 Cost Center Resolver。、完整 payload 必须进入审计日志。 | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`erpnext_validation_error` |

### `erpnext.accounting.create_purchase_invoice_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Purchase Invoice 草稿，不提交。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Purchase Invoice`, `Purchase Invoice Item`, `Purchase Taxes and Charges` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `data` |

Business Contract：

- 只创建 docstatus=0 的草稿；提交必须另行使用 submit_financial_document 并经过 financial_confirm。
- 创建前必须确认供应商、公司、发票日期、供应商发票号、明细、数量、价格、税费模板或税行、费用科目和成本中心。
- data.supplier 必须来自 Supplier Resolver；data.company、posting_date、bill_date、items[].expense_account、items[].cost_center 必须由对应 resolver 或已校验上下文生成。
- 如从采购收货生成，优先使用 create_purchase_invoice_from_purchase_receipt_draft 保留来源行引用。
- 制度配置项：价税差异、费用归集和应付账款科目规则以公司财务制度、ERPNext 税费模板和服务端校验为准，Agent 只能使用解析出的模板或用户确认值。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | 采购发票表单编排 | - | 必须是 Purchase Invoice draft payload；docstatus 会被服务端强制为 0。、data.supplier 必须来自 Supplier Resolver。、data.company 必须来自 Company Resolver。、data.posting_date/data.bill_date 必须来自 Date Resolver。、items[].expense_account 必须来自 Account Resolver。、items[].cost_center 必须来自 Cost Center Resolver。、完整 payload 必须进入审计日志。 | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`erpnext_validation_error` |

### `erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：从已提交 Purchase Receipt 创建 Purchase Invoice 草稿，不提交。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Purchase Receipt`, `Purchase Receipt Item`, `Purchase Invoice`, `Purchase Invoice Item`<br>先读取 Purchase Receipt，校验可开票数量，再创建 Purchase Invoice 草稿。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `purchase_receipt`、`posting_date`、`bill_no`、`bill_date`、`company`、`selected_items` |

Business Contract：

- 只创建 docstatus=0 的采购发票草稿；提交必须另行使用 submit_financial_document 并经过 financial_confirm。
- purchase_receipt 必须是已提交、非退货的 Purchase Receipt。
- selected_items 如填写，必须能唯一匹配来源收货行；数量必须大于 0 且不超过可开票数量。
- posting_date、bill_date 必须是明确 ISO 日期；bill_no 由供应商发票原文提供。
- 默认口径：有供应商发票原件时 bill_no/bill_date 视为必填；缺失时只能建草稿并提示补录，重复供应商发票号必须前置查询并由 ERPNext 再校验。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `purchase_receipt` | `string` | `True` | Purchase Receipt Resolver | `purchase_receipt` | 必须是 ERPNext Purchase Receipt.name。、必须是已提交且非退货单。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`erpnext_validation_error` |
| `posting_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。 | `ask_clarification`、`inject_context` |
| `bill_no` | `string` | `no` | 供应商发票原文 / 用户确认 | - | 不应由模型编造。 | `ask_clarification` |
| `bill_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。 | `ask_clarification`、`inject_context` |
| `company` | `string` | `no` | Company Resolver / Purchase Receipt Context | `company` | 必须是 ERPNext Company.name 全称；默认可来自收货单。 | `inject_context`、`resolve_entity` |
| `selected_items` | `array` | `no` | 收货行选择 / Runtime Builder | - | array_items_schema=true、数组每行 qty 必须大于 0。、purchase_receipt_item 必须来自 Purchase Receipt Item Resolver，或 item_code 唯一匹配来源行。、rate 如填写必须大于等于 0。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |

### `erpnext.accounting.create_period_closing_voucher_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Period Closing Voucher 草稿，不提交。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Period Closing Voucher` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `data` |

Business Contract：

- 只创建 docstatus=0 的期末结转草稿；提交必须另行使用 submit_financial_document 并经过 financial_confirm。
- 创建前必须确认公司、会计期间、结转日期、损益科目和目标结转科目。
- data.company、posting_date、fiscal_year、closing_account_head、cost_center 必须由 resolver 或已校验上下文生成。
- 制度配置项：期末结转允许的账户范围、期间冻结规则和多公司场景必须来自公司财务制度和 ERPNext 会计期间配置。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | 期末结转表单编排 | - | 必须是 Period Closing Voucher draft payload；docstatus 会被服务端强制为 0。、data.company 必须来自 Company Resolver。、data.posting_date 必须来自 Date Resolver。、data.fiscal_year 必须来自 Fiscal Year Resolver。、data.closing_account_head 必须来自 Account Resolver。、data.cost_center 如填写必须来自 Cost Center Resolver。、完整 payload 必须进入审计日志。 | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`erpnext_validation_error` |

### `erpnext.accounting.prepare_payment_allocation`

| 项目 | 内容 |
|---|---|
| 用途 | L1：准备 Payment Entry 引用发票分配，不创建、不提交付款单。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Sales Invoice`, `Purchase Invoice`<br>读取已提交且未结清的发票，返回分配建议。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `party_type`、`party`、`payment_type`、`invoice_doctype`、`invoice_names`、`company`、`paid_amount` |

Business Contract：

- 只准备付款分配候选，不创建 Payment Entry，不触发财务过账。
- party_type 必须是 Customer 或 Supplier；party 必须解析为对应 Customer/Supplier 主键。
- invoice_names 如填写，必须来自 Invoice Resolver；每张发票应为已提交且有未结清金额。
- paid_amount 必须大于等于 0；allocations 不得超过发票未结清金额。
- 制度配置项：部分核销、预收预付、折扣和差额处理策略必须来自公司财务制度；Agent 只能按已解析规则生成候选分配。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `party_type` | `enum` | `True` | 用户选择 / Runtime 推断 | - | 只能是 Customer 或 Supplier。 | `ask_clarification`、`validate_before_execute` |
| `party` | `string` | `True` | Customer/Supplier Resolver | `party` | 必须与 party_type 匹配。、Customer 场景必须是 ERPNext Customer.name；Supplier 场景必须是 ERPNext Supplier.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `payment_type` | `enum` | `no` | Runtime 推断 / 用户确认 | - | Customer 默认 Receive，Supplier 默认 Pay；与 party_type 不一致时必须追问。 | `ask_clarification`、`validate_before_execute` |
| `invoice_doctype` | `enum` | `no` | Runtime 推断 / 用户确认 | - | Customer 通常对应 Sales Invoice，Supplier 通常对应 Purchase Invoice。 | `ask_clarification`、`validate_before_execute` |
| `invoice_names` | `array` | `no` | Invoice Resolver / 用户选择 | `invoice` | array_items_schema=true、每个值必须是 ERPNext Sales Invoice.name 或 Purchase Invoice.name。、必须与 invoice_doctype 和 party 匹配。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `company` | `string` | `no` | Company Resolver / Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `paid_amount` | `number` | `no` | 用户确认金额 / Runtime 计算 | - | minimum=0、必须大于等于 0。 | `ask_clarification`、`validate_before_execute` |
| `allocations` | `object` | `no` | Runtime Builder / 用户确认 | - | 键必须对应已解析 invoice_names 或候选发票。、分配金额不得为负。 | `validate_before_execute`、`ask_clarification` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |
| `order_by` | `string` | `no` | - | - | - | - |

### `erpnext.accounting.prepare_invoice_taxes`

| 项目 | 内容 |
|---|---|
| 用途 | L1：准备销售/采购发票税行，不创建发票。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Sales Taxes and Charges Template`, `Purchase Taxes and Charges Template`<br>可读取税费模板并根据输入明细准备 taxes 行；最终总额仍由 ERPNext 草稿创建校验。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `invoice_type`、`taxes_and_charges`、`items`、`taxes`、`net_total` |

Business Contract：

- 只准备税行，不创建、不修改、不提交发票。
- invoice_type 必须与后续发票类型一致。
- taxes_and_charges 如填写，必须来自税费模板 resolver，不能使用未确认的模板名。
- 显式 taxes 行必须来自用户确认或受控模板展开，不能由模型任意拼税率和科目。
- 制度配置项：税率、含税/未税、进项/销项税科目和四舍五入口径必须来自公司财务制度与 ERPNext 税费模板，禁止模型自行编造税行。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `invoice_type` | `enum` | `True` | 用户选择 / Runtime 推断 | - | 只能使用 schema 枚举值。 | `ask_clarification`、`validate_before_execute` |
| `taxes_and_charges` | `string` | `no` | Tax Template Resolver | `tax_template` | 必须是对应销售/采购税费模板的 ERPNext name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `items` | `array` | `no` | 发票明细编排 | - | array_items_schema=true、用于计算税基；物料、科目、成本中心等外键必须已解析。 | `validate_before_execute`、`resolve_entity` |
| `taxes` | `array` | `no` | 用户确认 / 模板展开 | - | array_items_schema=true、显式税行必须经过财务确认或模板展开；不得由模型自由编造税率、科目。 | `ask_clarification`、`validate_before_execute` |
| `net_total` | `number` | `no` | Runtime 计算 / 用户确认 | - | minimum=0、必须大于等于 0。 | `validate_before_execute` |

### `erpnext.accounting.prepare_bank_reconciliation`

| 项目 | 内容 |
|---|---|
| 用途 | L1：准备银行流水与 Payment Entry 候选匹配，不执行核销。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Bank Transaction`, `Payment Entry`<br>只读读取 Bank Transaction 与已提交 Payment Entry 候选。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `company`、`bank_account`、`status`、`from_date`、`to_date`、`limit` |

Business Contract：

- 只准备银行对账候选，不匹配、不替换、不过账。
- company、bank_account 必须来自 resolver 或已校验上下文。
- 日期范围必须是明确 ISO 日期；to_date 不得早于 from_date。
- apply_bank_reconciliation 前必须由财务复核具体 Bank Transaction 和 Payment Entry 匹配关系。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `company` | `string` | `no` | Company Resolver / Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `bank_account` | `string` | `no` | Bank Account Resolver | `bank_account` | 必须是 ERPNext Bank Account.name 或系统认可的银行账户主键。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `status` | `string` | `no` | 用户选择 / Runtime 默认 | - | 用于筛选 Bank Transaction.status；当前 schema 未枚举，执行前需校验。 | `ask_clarification`、`validate_before_execute` |
| `from_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。 | `ask_clarification`、`inject_context` |
| `to_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。、不得早于 from_date。 | `ask_clarification`、`validate_before_execute` |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100、默认由 Runtime 控制，避免一次返回过多候选。 | - |
| `order_by` | `string` | `no` | - | - | - | - |

### `erpnext.accounting.apply_bank_reconciliation`

| 项目 | 内容 |
|---|---|
| 用途 | L5_FINANCIAL：在明确财务确认后应用银行核销匹配。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `financial_confirm` |
| Backend Mapping | DocType: `Bank Transaction`, `Payment Entry`<br>Method: `agent_bridge.api.reconcile_bank_transaction` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `bank_transaction`、`matches`、`replace_existing`、`remarks`、`confirmation` |

Business Contract：

- 必须带 financial_confirm；禁止在缺少确认元数据时执行。
- 只匹配既有 Payment Entry 到一个 Bank Transaction；不创建新的 Payment Entry 或 Journal Entry。
- bank_transaction 必须来自 Bank Transaction Resolver。
- matches[].payment_entry 必须来自 Payment Entry Resolver；allocated_amount 必须大于 0。
- replace_existing=true 会替换既有匹配，必须在确认摘要中明确说明。
- 执行前应展示银行流水、付款单、分配金额和替换策略供财务确认。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `bank_transaction` | `string` | `True` | Bank Transaction Resolver | `bank_transaction` | 必须是 ERPNext Bank Transaction.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `matches` | `array` | `True` | prepare_bank_reconciliation 候选 + 财务确认 | `payment_entry` | array_items_schema=true、数组至少 1 行。、matches[].payment_entry 必须是 ERPNext Payment Entry.name。、matches[].payment_document 必须与 payment_entry 指向同一付款文档。、matches[].allocated_amount 必须大于 0。 | `resolve_entity`、`ask_clarification`、`validate_before_execute` |
| `replace_existing` | `boolean` | `no` | 财务确认 | - | 默认为 false；true 时必须在确认摘要中说明替换原因。 | `ask_clarification` |
| `remarks` | `string` | `no` | 财务说明 | - | 建议记录核销依据或对账说明。 | - |
| `confirmation` | `object` | `True` | Financial Confirmation | - | 必须包含财务确认元数据，且确认摘要覆盖 bank_transaction、matches 和 replace_existing。 | `ask_clarification`、`permission_denied`、`validate_before_execute` |

### `erpnext.accounting.create_budget_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Budget 草稿，不提交预算控制。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Budget`, `Budget Account` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `data` |

Business Contract：

- 只创建 docstatus=0 的预算草稿；预算提交或启用控制必须另行确认。
- 创建前必须确认公司、会计年度、预算维度、预算账户/金额和控制动作。
- data.company、data.fiscal_year、accounts[].account、cost_center/project 等预算维度必须由 resolver 或已校验上下文生成。
- 制度配置项：预算 against 维度、月度分解、超预算动作和提交流程必须来自公司财务制度与 ERPNext Budget 配置。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | 预算表单编排 | - | 必须是 Budget draft payload；docstatus 会被服务端强制为 0。、data.company 必须来自 Company Resolver。、data.fiscal_year 必须来自 Fiscal Year Resolver。、accounts[].account 必须来自 Account Resolver。、cost_center 如填写必须来自 Cost Center Resolver。、完整 payload 必须进入审计日志。 | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`erpnext_validation_error` |

### `erpnext.accounting.update_budget_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：更新 Budget 草稿，保持 docstatus=0，不提交预算控制。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Budget`, `Budget Account` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `name`、`data` |

Business Contract：

- 只能更新 Budget 草稿；服务端会强制 docstatus=0。
- 更新前必须明确预算单名称、变更字段、变更原因和影响范围。
- name 必须来自预算查询结果或 Budget Resolver，不允许模型编造。
- data 中的 company、fiscal_year、account、cost_center 等外键必须由 resolver 或已校验上下文生成。
- 默认口径：该工具不得把已提交预算回写为草稿；已提交预算调整应走取消/修订或专门预算调整流程，并受 ERPNext 权限限制。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `name` | `string` | `True` | Budget Resolver / search_budgets 结果 | `budget` | 必须是 ERPNext Budget.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `data` | `object` | `True` | 预算变更表单编排 | - | 必须是 Budget draft update payload；docstatus 会被服务端强制为 0。、data.company 必须来自 Company Resolver。、data.fiscal_year 必须来自 Fiscal Year Resolver。、accounts[].account 必须来自 Account Resolver。、cost_center 如填写必须来自 Cost Center Resolver。、完整 payload 必须进入审计日志。 | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`erpnext_validation_error` |

### `erpnext.accounting.submit_financial_document`

| 项目 | 内容 |
|---|---|
| 用途 | L5_FINANCIAL：提交会影响总账或财务状态的财务单据。 |
| Allowed Roles | 财务 |
| Expose | `agent_visible` |
| Confirm | `financial_confirm` |
| Backend Mapping | DocType: `Journal Entry`, `Payment Entry`, `Sales Invoice`, `Purchase Invoice`, `Period Closing Voucher`<br>仅提交白名单财务 DocType。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `doctype`、`name`、`confirmation` |

Business Contract：

- 必须带 financial_confirm；禁止在缺少确认元数据时执行。
- 只允许提交 schema 枚举中的财务 DocType。
- 提交前必须展示单据类型、单据号、金额/影响摘要、公司、日期和关键外键供财务确认。
- name 必须来自对应 DocType 的 resolver 或刚创建的草稿结果；不能由模型编造。
- Journal Entry、Payment Entry、Sales Invoice、Purchase Invoice、Period Closing Voucher 提交后可能产生或改变总账影响。
- 默认口径：财务提交前必须运行可用的 GL 影响预览、税额复核和审批流状态检查；缺少自动校验能力时升级为财务人工确认。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `enum` | `True` | Runtime 枚举 / 草稿上下文 | - | 只能使用 schema 枚举值。 | `ask_clarification`、`validate_before_execute` |
| `name` | `string` | `True` | Financial Document Resolver / 草稿创建结果 | `financial_document` | 必须是 doctype 对应的 ERPNext 文档 name。、Sales Invoice/Purchase Invoice 必须来自 Invoice Resolver。、Payment Entry 必须来自 Payment Entry Resolver。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `confirmation` | `object` | `True` | Financial Confirmation | - | 必须包含财务确认元数据，且确认摘要覆盖 doctype、name 和财务影响。 | `ask_clarification`、`permission_denied`、`validate_before_execute` |

### `erpnext.assets.search_assets`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询固定资产主数据，用于按公司、类别、位置、状态、物料、保管人或资产名称检索候选。 |
| Allowed Roles | 资产管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Asset` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `query`、`company`、`asset_category`、`location`、`status`、`item_code`、`custodian`、`limit` |

Business Contract：

- 查询结果只用于展示候选和上下文，不代表已确认资产。
- 用户只提供简称、位置别名或模糊资产名时，必须展示候选，不允许强行选择。
- 默认口径：Asset.custodian 优先解析 Employee；站点未启用 Employee 或存在自定义字段时，再按站点元数据回退到 User 或自定义主数据。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `query` | `string` | `no` | 用户原话 | - | 仅作为 asset_name 模糊检索输入。 | - |
| `company` | `string` | `no` | Runtime Context / Company Resolver | `company` | 必须是 ERPNext Company.name 全称。 | - |
| `asset_category` | `string` | `no` | Asset Category Resolver | `asset_category` | 必须是已存在的 ERPNext Asset Category.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `location` | `string` | `no` | Asset Location Resolver | `asset_location` | 必须是已存在的 ERPNext Asset Location.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `status` | `string` | `no` | - | - | - | - |
| `item_code` | `string` | `no` | Item Resolver | `item` | 必须是已存在的 ERPNext Item.item_code。 | - |
| `custodian` | `string` | `no` | Custodian Resolver | `employee` | 必须解析为当前 ERPNext 站点 Asset.custodian 字段接受的真实主键。 | - |
| `filters` | `object|array` | `no` | Runtime Builder | - | 禁止模型直接手写任意 Frappe filter DSL。 | - |
| `fields` | `array` | `no` | Field Resolver | `field` | array_items_schema=true、字段必须存在于 Asset meta。 | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | Runtime 分页 | - | minimum=0 | - |
| `order_by` | `string` | `no` | Runtime / 用户排序意图 | - | - | - |

### `erpnext.assets.search_asset_categories`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 Asset Category 主数据候选。 |
| Allowed Roles | 资产管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Asset Category` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `query`、`limit` |

Business Contract：

- 查询结果只用于候选展示；低置信或多候选必须让用户确认。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `query` | `string` | `no` | 用户原话 | `asset_category` | 仅作为 Asset Category 候选检索输入。 | - |
| `filters` | `object|array` | `no` | Runtime Builder | - | 禁止模型直接手写任意 Frappe filter DSL。 | - |
| `fields` | `array` | `no` | Field Resolver | `field` | array_items_schema=true | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | Runtime 分页 | - | minimum=0 | - |
| `order_by` | `string` | `no` | Runtime / 用户排序意图 | - | - | - |

### `erpnext.assets.search_asset_locations`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 Asset Location 主数据候选。 |
| Allowed Roles | 资产管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Asset Location` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `query`、`limit` |

Business Contract：

- 查询结果只用于候选展示；位置简称或层级路径不明确时必须展示候选。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `query` | `string` | `no` | 用户原话 | `asset_location` | 仅作为 Asset Location 候选检索输入。 | - |
| `filters` | `object|array` | `no` | Runtime Builder | - | 禁止模型直接手写任意 Frappe filter DSL。 | - |
| `fields` | `array` | `no` | Field Resolver | `field` | array_items_schema=true | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | Runtime 分页 | - | minimum=0 | - |
| `order_by` | `string` | `no` | Runtime / 用户排序意图 | - | - | - |

### `erpnext.assets.get_financial_snapshot`

| 项目 | 内容 |
|---|---|
| 用途 | L0：读取单个资产的采购、财务账簿、折旧计划和价值快照，不创建 GL、不过账折旧、不创建销售或处置单据。 |
| Allowed Roles | 资产管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Asset`, `Asset Depreciation Schedule` |
| Repair | `resolve_entity`、`ask_clarification`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `asset`、`finance_book`、`include_depreciation_schedules`、`include_schedule_rows`、`schedule_limit` |

Business Contract：

- 仅用于资产财务状态查看，不允许据此自动提交折旧、处置、销售或价值调整。
- 默认口径：finance_book 优先使用公司默认 Finance Book；用户指定时必须通过 Finance Book resolver 精确命中。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `asset` | `string` | `True` | Asset Resolver | `asset` | 必须是已存在的 ERPNext Asset.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `finance_book` | `string` | `no` | Finance Book Resolver / Runtime Context | `finance_book` | 如填写，必须是当前站点有效的 Finance Book 名称。 | - |
| `include_depreciation_schedules` | `boolean` | `no` | Runtime 默认值 / 用户选择 | - | - | - |
| `include_schedule_rows` | `boolean` | `no` | Runtime 默认值 / 用户选择 | - | - | - |
| `schedule_limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=50 | - |

### `erpnext.assets.get_depreciation_schedule`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询资产折旧计划和可选计划行，不过账折旧。 |
| Allowed Roles | 资产管理员 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Asset Depreciation Schedule` |
| Repair | `resolve_entity`、`ask_clarification`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `asset`、`finance_book`、`status`、`include_rows`、`only_due_before`、`limit` |

Business Contract：

- 只能读取折旧计划状态；过账折旧或生成财务影响必须使用受控财务/提交流程。
- 站点配置项：折旧计划状态枚举必须从当前 ERPNext Asset Depreciation Schedule 元数据或报表返回值读取。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `asset` | `string` | `True` | Asset Resolver | `asset` | 必须是已存在的 ERPNext Asset.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `finance_book` | `string` | `no` | Finance Book Resolver / Runtime Context | `finance_book` | - | - |
| `status` | `string` | `no` | 用户选择 / Runtime | - | 必须是当前 ERPNext 站点支持的 Asset Depreciation Schedule 状态。 | - |
| `include_rows` | `boolean` | `no` | Runtime 默认值 / 用户选择 | - | - | - |
| `only_due_before` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。 | - |
| `fields` | `array` | `no` | Field Resolver | `field` | array_items_schema=true | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100 | - |
| `offset` | `integer` | `no` | Runtime 分页 | - | minimum=0 | - |
| `order_by` | `string` | `no` | Runtime / 用户排序意图 | - | - | - |

### `erpnext.assets.create_asset_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Asset 草稿，不提交、不资本化。 |
| Allowed Roles | 资产管理员 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Asset`<br>Method: `ERPNextClient.create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `data` |

Business Contract：

- 创建前必须确认资产名称、物料、资产类别、公司、位置、购置金额和可用日期等关键字段。
- data 中的 item_code、asset_category、location、custodian、cost_center、purchase_date、available_for_use_date 等外键或日期必须来自对应 resolver 或用户明确确认。
- 提交/资本化必须走 erpnext.assets.submit_document，并获得 submit_confirm。
- 默认口径：创建 Asset 草稿前读取 Asset 元数据和 Asset Category 默认值；CWIP/折旧字段由类别、公司和账簿配置补齐，无法补齐时追问。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | 资产草稿表单编排 | - | 必须是 Asset 的草稿 payload；禁止模型自由拼不属于 Asset meta 的字段。、主数据外键必须使用解析后的 ERPNext 主键，不允许使用用户口语简称。、金额、日期、折旧相关字段必须来自用户确认或 Runtime 上下文。 | `resolve_entity`、`ask_clarification`、`validate_before_execute` |

### `erpnext.assets.create_movement_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Asset Movement 草稿，用于资产领用、接收或转移，不提交。 |
| Allowed Roles | 资产管理员 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Asset Movement`<br>Method: `ERPNextClient.create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `data` |

Business Contract：

- 创建前必须确认移动类型、资产、源/目标位置、保管人和业务原因。
- data 中涉及 asset、source_location、target_location、from_employee、to_employee、transaction_date 等字段必须由对应 resolver 或用户明确确认。
- 提交移动单必须走 erpnext.assets.submit_document，并获得 submit_confirm。
- 默认口径：Asset Movement 按 movement purpose 和 DocType 元数据动态校验必填字段；源/目标位置或保管人缺失时先追问。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | 资产移动草稿表单编排 | - | 必须是 Asset Movement 的草稿 payload。、资产和位置必须解析成 ERPNext 主键。、不得在草稿工具中绕过提交确认。 | `resolve_entity`、`ask_clarification`、`validate_before_execute` |

### `erpnext.assets.create_maintenance_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Asset Maintenance 计划草稿，不提交。 |
| Allowed Roles | 资产管理员 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Asset Maintenance`<br>Method: `ERPNextClient.create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `data` |

Business Contract：

- 创建前必须确认资产、维护任务、周期、责任人和计划日期。
- data 中涉及 asset、asset_category、assign_to、maintenance_team、start_date/end_date 等字段必须由对应 resolver 或用户明确确认。
- 提交维护计划必须走 erpnext.assets.submit_document，并获得 submit_confirm。
- 站点配置项：维护计划子表字段和周期枚举从 Asset Maintenance 元数据读取；未知周期不得由模型自造。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | 资产维护计划表单编排 | - | 必须是 Asset Maintenance 的草稿 payload。、维护任务和责任人不明确时必须追问。 | `resolve_entity`、`ask_clarification`、`validate_before_execute` |

### `erpnext.assets.create_maintenance_log_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Asset Maintenance Log 草稿，不提交。 |
| Allowed Roles | 资产管理员 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Asset Maintenance Log`<br>Method: `ERPNextClient.create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `data` |

Business Contract：

- 创建前必须确认资产、维护日期、维护状态、执行人和工作说明。
- data 中涉及 asset、asset_maintenance、task、maintenance_date、assign_to 等字段必须由对应 resolver 或用户明确确认。
- 提交维护日志必须走 erpnext.assets.submit_document，并获得 submit_confirm。
- 默认口径：维护日志优先关联已解析的 Asset Maintenance/任务；无计划引用时只允许创建独立维护日志草稿并提示人工确认。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | 资产维护日志表单编排 | - | 必须是 Asset Maintenance Log 的草稿 payload。、维护结果和异常说明不能由模型虚构。 | `resolve_entity`、`ask_clarification`、`validate_before_execute` |

### `erpnext.assets.create_repair_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Asset Repair 草稿，不提交；提交后可能影响资产价值或维修成本。 |
| Allowed Roles | 资产管理员 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Asset Repair`<br>Method: `ERPNextClient.create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `data` |

Business Contract：

- 创建前必须确认资产、故障/维修说明、维修日期、维修成本和责任人。
- data 中涉及 asset、failure_date、repair_status、cost_center、warehouse、item_code 等字段必须由对应 resolver 或用户明确确认。
- 提交维修单必须走 erpnext.assets.submit_document，并获得 submit_confirm。
- 制度配置项：维修成本是否资本化、是否影响资产价值必须来自公司财务制度和 ERPNext 资产配置；Agent 只能生成候选处理方式。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | 资产维修草稿表单编排 | - | 必须是 Asset Repair 的草稿 payload。、维修成本、物料、仓库、费用归属必须明确，不能使用模糊描述。 | `resolve_entity`、`ask_clarification`、`validate_before_execute` |

### `erpnext.assets.create_value_adjustment_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Asset Value Adjustment 草稿，不提交；提交属于高风险财务影响。 |
| Allowed Roles | 资产管理员 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Asset Value Adjustment`<br>Method: `ERPNextClient.create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `data` |

Business Contract：

- 创建前必须确认资产、调整日期、调整金额/价值、调整原因和财务归属。
- data 中涉及 asset、finance_book、cost_center、date、current_asset_value、new_asset_value 等字段必须由对应 resolver 或用户明确确认。
- 提交价值调整必须走 erpnext.assets.submit_document，并获得 submit_confirm。
- 制度配置项：价值调整的会计分录、账簿和权限要求以 ERPNext 财务配置为准，提交前必须展示财务影响并获得确认。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | 资产价值调整草稿表单编排 | - | 必须是 Asset Value Adjustment 的草稿 payload。、调整金额和原因必须进入审计日志。 | `resolve_entity`、`ask_clarification`、`validate_before_execute` |

### `erpnext.assets.prepare_disposal_or_sale`

| 项目 | 内容 |
|---|---|
| 用途 | L5：准备资产报废、处置或销售评审，读取资产并返回后续动作和风险上下文；不创建 GL、不创建发票、不提交处置。 |
| Allowed Roles | 资产管理员 |
| Expose | `agent_visible` |
| Confirm | `supervisor_confirm` |
| Backend Mapping | DocType: `Asset`<br>该工具只读取 Asset 并准备处置/销售风险上下文，实际过账或销售由财务/销售受控工具处理。 |
| Repair | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `asset`、`action`、`posting_date`、`proceeds_amount`、`party_type`、`party`、`reason` |

Business Contract：

- 资产处置、报废或销售必须展示资产、原因、日期、预计收入和潜在财务影响并获得主管确认。
- 该工具不能替代财务过账、销售发票或资产提交工具。
- 默认口径：dispose、scrap、sell 均先生成处置准备结果和确认摘要；正式单据链与审批人由资产处置配置 resolver 返回。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `asset` | `string` | `True` | Asset Resolver | `asset` | 必须是已存在的 ERPNext Asset.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `action` | `enum` | `True` | 用户选择 | - | 只能是 dispose、scrap、sell。 | - |
| `posting_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。 | - |
| `proceeds_amount` | `number` | `no` | 用户确认金额 | - | minimum=0、金额不得为负数。 | - |
| `party_type` | `string` | `no` | DocType Resolver | `doctype` | 销售场景如填写，必须是当前 ERPNext 站点支持的交易方类型。 | - |
| `party` | `string` | `no` | Document Resolver | `docname` | 销售场景如填写，必须是 party_type 下已存在的单据名。 | - |
| `reason` | `string` | `no` | 用户确认文本 | - | 处置或销售原因必须明确进入审计。 | - |

### `erpnext.assets.submit_document`

| 项目 | 内容 |
|---|---|
| 用途 | L4/L5：提交资产生命周期单据；Asset 和 Asset Value Adjustment 可能产生高风险财务影响。 |
| Allowed Roles | 资产管理员 |
| Expose | `agent_visible` |
| Confirm | `submit_confirm` |
| Backend Mapping | DocType: `Asset`, `Asset Movement`, `Asset Maintenance`, `Asset Maintenance Log`, `Asset Repair`, `Asset Value Adjustment`<br>Method: `agent_bridge.api.submit_document` |
| Repair | `resolve_entity`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `doctype`、`name`、`confirmation` |

Business Contract：

- 提交前必须展示单据类型、单据名、资产影响和可能的财务/库存/责任人变化。
- Asset 和 Asset Value Adjustment 提交属于高风险财务影响，必须由资产管理员显式确认。
- Asset Movement、Asset Maintenance、Asset Maintenance Log、Asset Repair 提交属于资产生命周期变更，必须显式确认。
- 站点配置项：资产单据提交后的会计、库存或维护状态影响以当前 ERPNext 版本、DocType 元数据和站点自定义为准。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `enum` | `True` | DocType Resolver | `doctype` | 只允许 Asset、Asset Movement、Asset Maintenance、Asset Maintenance Log、Asset Repair、Asset Value Adjustment。 | - |
| `name` | `string` | `True` | Document Resolver | `docname` | 必须是 doctype 下已存在且可提交的草稿单据名。 | - |
| `confirmation` | `object` | `True` | Confirmation Policy | - | 必须包含用户对高风险提交动作的显式确认元数据。 | - |

### `erpnext.stock.get_balance`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询库存余额、预计数量和估值快照。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Bin`, `Item`, `Warehouse`<br>主要读取 Bin，必要时关联 Item 与 Warehouse。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`permission_denied` |
| 审计重点 | `item_code`、`item_query`、`warehouse`、`item_group`、`limit` |

Business Contract：

- 如果 item_code 缺失且 item_query 缺失，必须追问用户要查哪个物料。
- 如果 item_query 命中多个物料，必须展示候选，不允许强行选择。
- warehouse 必须解析成 ERPNext Warehouse.name 全称；用户简称只能作为 resolver 输入。
- 用户查询某物料所有仓库库存时，warehouse 可以为空。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `conditional` | Item Resolver | `item` | 外键：必须是已存在的 ERPNext Item.item_code。、禁止模型凭空编物料编码。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `item_query` | `string` | `conditional` | 用户原话 | `item` | 仅作为检索输入，不能直接当成 item_code 使用。 | `resolve_entity`、`present_candidates` |
| `warehouse` | `string` | `conditional` | Warehouse Resolver / 员工默认仓库 | `warehouse` | 必须使用 ERPNext Warehouse.name 全称。、禁止把中心仓、项目仓等简称直接写入 ToolCall。 | `resolve_entity`、`ask_clarification`、`inject_context` |
| `specs` | `object` | `no` | Slot Extractor | - | 只用于辅助物料检索，不作为 ERPNext 主键。 | - |
| `item_group` | `string` | `no` | Item Group Resolver | `item_group` | 用于缩小候选范围。 | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=200、默认由 Runtime 控制，避免一次返回过多库存行。 | - |

### `erpnext.stock.get_item_locations`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询指定物料在哪些仓库/Bin 有库存。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Bin`, `Item`, `Warehouse` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`permission_denied` |
| 审计重点 | `item_code`、`item_query`、`selected_item_code`、`warehouse`、`include_zero`、`limit` |

Business Contract：

- 必须解析到唯一 Item 后才能查询库位；候选不唯一时必须展示候选。
- selection_confirmed 只能由人工选择或上游策略注入，模型不能自行置 true。
- include_zero=true 会暴露零库存库位，默认应保持 false，除非用户明确要求。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `conditional` | Item Resolver | `item` | 必须是已存在且未禁用的 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `item_query` | `string` | `conditional` | 用户原话 | `item` | 仅作为解析输入，不直接写入 ERPNext 外键。 | `resolve_entity`、`present_candidates` |
| `selected_item_code` | `string` | `conditional` | Item Resolver 候选确认 | `item` | 必须来自 erpnext.stock.resolve_item 返回的候选。 | `resolve_entity`、`present_candidates` |
| `selection_confirmed` | `boolean` | `no` | 用户确认 / Runtime Policy | - | 只有已确认候选时才能为 true。 | `ask_clarification`、`validate_before_execute` |
| `specs` | `object` | `no` | - | - | - | - |
| `item_group` | `string` | `no` | Item Group Resolver | `item_group` | 用于辅助物料解析。 | - |
| `include_zero` | `boolean` | `no` | - | - | - | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=200、限制返回库位数量。 | - |

### `erpnext.stock.get_ledger_entries`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询库存流水，用于库存移动审计。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Stock Ledger Entry`, `Item`, `Warehouse` |
| Repair | `resolve_entity`、`ask_clarification`、`inject_context`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `item_code`、`warehouse`、`voucher_type`、`voucher_no`、`limit` |

Business Contract：

- 只读查询，不允许由该工具创建、取消或调整库存流水。
- 按凭证查询时，voucher_type 与 voucher_no 应同时提供。
- warehouse 如由用户简称给出，必须先解析为 Warehouse.name。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `no` | Item Resolver | `item` | 必须是 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates` |
| `warehouse` | `string` | `no` | Warehouse Resolver | `warehouse` | 必须是 ERPNext Warehouse.name。 | `resolve_entity`、`ask_clarification` |
| `voucher_type` | `string` | `no` | 用户指定 / Runtime Context | - | 应使用 ERPNext 凭证类型原名。 | - |
| `voucher_no` | `string` | `no` | 用户指定 / Runtime Context | - | 必须是已存在业务凭证编号，不能凭空编造。 | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=200、默认限制返回数量，避免拉取过多流水。 | - |

### `erpnext.stock.get_stock_settings`

| 项目 | 内容 |
|---|---|
| 用途 | L0：读取库存设置单例，用于判断批次、序列号、预留和估值行为。 |
| Allowed Roles | 仓管、仓库主管、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Stock Settings` |
| Repair | `permission_denied`、`erpnext_validation_error` |
| 审计重点 | - |

Business Contract：

- 只允许读取设置，不允许修改库存控制规则。
- 输出只能作为后续工具的校验上下文，不应直接覆盖用户确认。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| - | - | - | - | - | - | - |

### `erpnext.stock.resolve_item`

| 项目 | 内容 |
|---|---|
| 用途 | L1：解析库存物料候选，不修改 ERPNext。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Item`, `Item Group`<br>可选使用 PostgreSQL material catalog 召回，再以 ERPNext Item 为最终候选。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `query`、`specs`、`item_group`、`enabled_only`、`limit` |

Business Contract：

- 返回候选用于后续 ToolCall，不代表已经获得库存动作授权。
- 只有 ERPNext 候选唯一且可用时，才允许自动带入 selected_item_code。
- catalog_database_url 只能来自运行时安全上下文，不应从员工自然语言中采纳。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `query` | `string` | `True` | 用户原话 | `item` | 必须是物料名称、编码、规格或别名检索词。 | `ask_clarification`、`resolve_entity`、`present_candidates` |
| `specs` | `object` | `no` | Slot Extractor | - | 只用于辅助召回和消歧。 | - |
| `item_group` | `string` | `no` | Item Group Resolver | `item_group` | 必须解析到 ERPNext Item Group.name 后用于缩小候选。 | `resolve_entity`、`present_candidates` |
| `enabled_only` | `boolean` | `no` | Runtime 默认值 | - | 默认 true，避免后续库存动作使用禁用物料。 | - |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=50 | - |
| `catalog_database_url` | `string` | `no` | Runtime Secret | - | 禁止由模型或用户文本直接提供连接串。 | `inject_context`、`permission_denied` |

### `erpnext.stock.create_entry_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Stock Entry 草稿，用于收料、发料、转移、制造或重包；不提交。 |
| Allowed Roles | 仓管、仓库主管 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Stock Entry`, `Stock Entry Detail`, `Item`, `Warehouse`, `Batch`, `Serial No`, `UOM` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `stock_entry_type`、`purpose`、`company`、`posting_date`、`items`、`remarks` |

Business Contract：

- 采购角色不能创建库存移动草稿。
- 创建前必须确认 stock_entry_type/purpose、公司、日期、每行物料、仓库和数量。
- items 至少 1 行；每行 item_code 必须来自 Item Resolver 或已确认 selected_item_code。
- 数量必须为正数；涉及批次、序列号、UOM、源/目标仓库时必须先解析主数据。
- 默认口径：按 ERPNext Stock Entry purpose 校验仓库方向：Material Issue 需要 s_warehouse，Material Receipt 需要 t_warehouse，Material Transfer 两者都需要；自定义类型按 Stock Entry Type 元数据校验。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `stock_entry_type` | `string` | `no` | 用户选择 / Runtime Policy | - | 应匹配 ERPNext Stock Entry Type。、默认口径：允许使用已存在且启用的自定义 Stock Entry Type，但必须由 resolver 精确命中并通过权限校验。 | `ask_clarification`、`validate_before_execute` |
| `purpose` | `string` | `no` | 用户选择 / Runtime Policy | - | 应与 stock_entry_type 和业务场景一致。 | `ask_clarification`、`validate_before_execute` |
| `company` | `string` | `conditional` | Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `posting_date` | `string` | `conditional` | Date Resolver | `date` | 必须是 ISO 日期。 | `inject_context`、`ask_clarification` |
| `posting_time` | `string` | `no` | - | - | - | - |
| `remarks` | `string` | `no` | 用户说明 | - | 库存移动原因、业务单据来源或现场说明应进入 remarks。 | - |
| `items` | `array` | `True` | Item/Warehouse/Batch/Serial/UOM Resolver + Slot Extractor | - | array_items_schema=true、数组至少 1 行。、每行 qty 必须大于 0。、每行 item_code、s_warehouse、t_warehouse、batch_no、serial_no、uom/stock_uom 必须分别经 item、warehouse、batch、serial_no、uom resolver。、模型不得凭空编造批次号、序列号或仓库名。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |

### `erpnext.stock.create_reconciliation_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建库存盘点/调整草稿，提交后可能改变账面库存和估值。 |
| Allowed Roles | 仓管、仓库主管 |
| Expose | `agent_visible` |
| Confirm | `supervisor_confirm` |
| Backend Mapping | DocType: `Stock Reconciliation`, `Stock Reconciliation Item`, `Item`, `Warehouse`, `Batch`, `Serial No` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `company`、`posting_date`、`purpose`、`items`、`remarks` |

Business Contract：

- 采购员、项目经理、班组长不能直接使用。
- 创建草稿前必须记录盘点依据或调整原因。
- 差异数量或估值异常过大时必须升级主管确认。
- items 每行必须包含真实 item_code、warehouse 和盘点数量；涉及批次/序列号时必须解析主数据。
- 制度配置项：valuation_rate 调整默认需要库存主管确认；单行估值差异超过 1000 或 10% 时升级财务确认，阈值可由站点配置覆盖。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `company` | `string` | `conditional` | Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `posting_date` | `string` | `conditional` | Date Resolver | `date` | 必须是 ISO 日期。 | `inject_context`、`ask_clarification` |
| `posting_time` | `string` | `no` | - | - | - | - |
| `purpose` | `string` | `no` | 用户选择 / Runtime Policy | - | 应明确是盘点、数量调整还是估值调整。 | `ask_clarification`、`validate_before_execute` |
| `expense_account` | `string` | `no` | - | - | - | - |
| `cost_center` | `string` | `no` | - | - | - | - |
| `remarks` | `string` | `conditional` | 盘点说明 | - | 必须记录盘点依据或调整原因。 | `ask_clarification` |
| `items` | `array` | `True` | 库存盘点表单编排 | - | array_items_schema=true、不允许模型自由拼任意字段。、items 每行必须包含真实 item_code、warehouse、盘点数量和差异原因。、每行 item_code、warehouse、batch_no、serial_no 必须分别经 item、warehouse、batch、serial_no resolver。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |

### `erpnext.stock.search_batches`

| 项目 | 内容 |
|---|---|
| 用途 | L0：按物料或批次关键字查询 Batch 追溯记录。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Batch`, `Item` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `item_code`、`item_query`、`query`、`limit` |

Business Contract：

- 只读查询，不允许通过该工具更新批次状态或有效期。
- 按物料查批次时，item_code 必须解析到唯一 Item。
- query 只能作为批次检索词，不能直接当成确认的 batch_no。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `no` | Item Resolver | `item` | 必须是 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates` |
| `item_query` | `string` | `no` | 用户原话 | `item` | 仅用于解析 item_code。 | `resolve_entity`、`present_candidates` |
| `query` | `string` | `no` | 用户原话 | `batch` | 批次关键词需经过候选展示后才能作为 batch_no 使用。 | `resolve_entity`、`present_candidates` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |

### `erpnext.stock.list_batch_balances`

| 项目 | 内容 |
|---|---|
| 用途 | L0：汇总物料批次在仓库中的可用数量和库存流水。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Batch`, `Stock Ledger Entry`, `Item`, `Warehouse` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `item_code`、`item_query`、`selected_item_code`、`batch_no`、`warehouse`、`as_of_date`、`include_expired`、`include_zero` |

Business Contract：

- 只读查询，不移动库存，不创建保留或拣货。
- 必须先解析 Item；批次不明确时展示候选。
- include_expired=true 只用于审计/追溯，不应默认用于发料推荐。
- as_of_date 必须按 ISO 日期解析。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `conditional` | Item Resolver | `item` | 必须是 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `item_query` | `string` | `conditional` | 用户原话 | `item` | 仅用于解析 item_code。 | `resolve_entity`、`present_candidates` |
| `selected_item_code` | `string` | `conditional` | Item Resolver 候选确认 | `item` | 必须来自已确认 Item 候选。 | `resolve_entity`、`present_candidates` |
| `selection_confirmed` | `boolean` | `no` | - | - | - | - |
| `batch_no` | `string` | `no` | Batch Resolver | `batch` | 必须是 ERPNext Batch.name 或 batch_id。 | `resolve_entity`、`present_candidates` |
| `query` | `string` | `no` | 用户原话 | `batch` | 作为批次候选检索词使用。 | `resolve_entity`、`present_candidates` |
| `warehouse` | `string` | `no` | Warehouse Resolver | `warehouse` | 必须是 ERPNext Warehouse.name。 | `resolve_entity`、`ask_clarification` |
| `include_expired` | `boolean` | `no` | - | - | - | - |
| `include_zero` | `boolean` | `no` | - | - | - | - |
| `as_of_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。 | `ask_clarification` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |
| `batch_limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |
| `ledger_limit` | `integer` | `no` | - | - | minimum=1、maximum=1000 | - |

### `erpnext.stock.search_serial_numbers`

| 项目 | 内容 |
|---|---|
| 用途 | L0：按物料、仓库、状态或序列号关键字查询 Serial No。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Serial No`, `Item`, `Warehouse` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `item_code`、`item_query`、`warehouse`、`status`、`query`、`limit` |

Business Contract：

- 只读查询，不允许更新序列号状态、仓库或关联单据。
- 按物料或仓库过滤时必须先解析外键。
- query 只能作为序列号检索词，不代表已确认 serial_no。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `no` | Item Resolver | `item` | 必须是 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates` |
| `item_query` | `string` | `no` | 用户原话 | `item` | 仅用于解析 item_code。 | `resolve_entity`、`present_candidates` |
| `warehouse` | `string` | `no` | Warehouse Resolver | `warehouse` | 必须是 ERPNext Warehouse.name。 | `resolve_entity`、`ask_clarification` |
| `status` | `string` | `no` | - | - | - | - |
| `query` | `string` | `no` | 用户原话 | `serial_no` | 用于检索 Serial No 候选。 | `resolve_entity`、`present_candidates` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |

### `erpnext.stock.create_batch`

| 项目 | 内容 |
|---|---|
| 用途 | L3：为已有物料创建 Batch 追溯主数据；不移动库存。 |
| Allowed Roles | 仓管、仓库主管 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Batch`, `Item` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `data` |

Business Contract：

- 创建前必须确认关联 Item。
- data.item 或 data.item_code 必须经 item resolver；不能直接采纳未确认物料名称。
- 默认口径：批号优先使用 ERPNext naming series/自动批号；有效期仅对启用保质期或批次有效期的 Item 必填，禁用批次必须给出原因。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | Batch 表单编排 | `item` | 必须包含已解析 Item 外键。、不允许模型凭空生成业务批号；如需系统自动命名，应遵循 ERPNext 配置。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |

### `erpnext.stock.update_batch`

| 项目 | 内容 |
|---|---|
| 用途 | L4：更新 Batch 追溯主数据；可能影响已发生库存追溯。 |
| Allowed Roles | 仓库主管 |
| Expose | `agent_visible` |
| Confirm | `submit_confirm` |
| Backend Mapping | DocType: `Batch` |
| Repair | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `name`、`data`、`confirmation` |

Business Contract：

- 必须有明确 confirmation，包含确认人、时间、原因和确认文本。
- 已发生库存移动的批次变更必须保留审计说明。
- 制度配置项：有库存流水的 Batch 禁止修改 item/batch_id；expiry_date、disabled、备注和自定义字段可在主管确认后修改，质量/财务字段需对应审批。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `name` | `string` | `True` | Batch Resolver | `batch` | 必须是已存在的 ERPNext Batch.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `data` | `object` | `True` | Batch 变更表单 | - | 只能包含允许变更的 Batch 字段。、涉及 item 时必须经 item resolver。 | `validate_before_execute`、`resolve_entity`、`ask_clarification` |
| `confirmation` | `object` | `True` | Confirmation Gate | - | 必须包含 confirmed_by、confirmed_at、confirmation_text 和 reason。 | `ask_clarification`、`validate_before_execute`、`permission_denied` |

### `erpnext.stock.create_serial_no`

| 项目 | 内容 |
|---|---|
| 用途 | L3：为已有物料创建 Serial No 追溯主数据；不提交库存移动。 |
| Allowed Roles | 仓管、仓库主管 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Serial No`, `Item`, `Warehouse` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `data` |

Business Contract：

- 创建前必须确认关联 Item；涉及仓库时必须解析 Warehouse。
- data.item_code/item、data.warehouse 必须分别经 item、warehouse resolver。
- 默认口径：序列号优先使用 ERPNext naming series/自动序列；初始仓库在入库场景必填，状态从 Serial No 元数据读取。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | Serial No 表单编排 | `serial_no` | 必须包含已解析 Item 外键。、不允许模型凭空生成序列号；如需系统自动命名，应遵循 ERPNext 配置。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |

### `erpnext.stock.update_serial_no`

| 项目 | 内容 |
|---|---|
| 用途 | L4：更新 Serial No 追溯主数据；可能影响库存追溯和资产识别。 |
| Allowed Roles | 仓库主管 |
| Expose | `agent_visible` |
| Confirm | `submit_confirm` |
| Backend Mapping | DocType: `Serial No` |
| Repair | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `name`、`data`、`confirmation` |

Business Contract：

- 必须有明确 confirmation，包含确认人、时间、原因和确认文本。
- 已发生库存移动的序列号变更必须保留审计说明。
- 制度配置项：有交易流水的 Serial No 禁止修改 item/serial_no；仓库、状态、备注和自定义字段可按权限修改，质量/资产字段需对应审批。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `name` | `string` | `True` | Serial No Resolver | `serial_no` | 必须是已存在的 ERPNext Serial No.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `data` | `object` | `True` | Serial No 变更表单 | - | 只能包含允许变更的 Serial No 字段。、涉及 item 或 warehouse 时必须分别经 item、warehouse resolver。 | `validate_before_execute`、`resolve_entity`、`ask_clarification` |
| `confirmation` | `object` | `True` | Confirmation Gate | - | 必须包含 confirmed_by、confirmed_at、confirmation_text 和 reason。 | `ask_clarification`、`validate_before_execute`、`permission_denied` |

### `erpnext.stock.list_pick_lists`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 Pick List 单据，用于拣货工作流查看。 |
| Allowed Roles | 仓管、仓库主管、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Pick List` |
| Repair | `ask_clarification`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `purpose`、`status`、`customer`、`limit` |

Business Contract：

- 只读查询，不提交、不取消、不修改拣货单。
- purpose/status 应使用 ERPNext Pick List 的合法取值或站点配置值。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `purpose` | `string` | `no` | 用户选择 | - | 应匹配 ERPNext Pick List purpose。 | - |
| `status` | `string` | `no` | 用户选择 | - | 应匹配 ERPNext Pick List status。 | - |
| `customer` | `string` | `no` | - | - | - | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100、限制返回数量。 | - |

### `erpnext.stock.create_pick_list_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Pick List 草稿，用于交付、转移或生产拣货；不提交。 |
| Allowed Roles | 仓管、仓库主管 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Pick List`, `Pick List Item`, `Item`, `Warehouse`, `Batch`, `Serial No`, `UOM` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `purpose`、`customer`、`work_order`、`material_request`、`sales_order`、`parent_warehouse`、`locations` |

Business Contract：

- 创建前必须确认拣货目的、来源单据或 locations 明细。
- locations 每行 qty 必须为正数，物料、仓库、批次、序列号、UOM 必须经 resolver。
- parent_warehouse 如有值必须解析为 Warehouse.name。
- 默认口径：Pick List 的 purpose 决定来源凭证，Work Order、Material Request、Sales Order 等来源字段必须互斥且由 resolver 精确命中。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `purpose` | `string` | `no` | 用户选择 / Runtime Policy | - | 应匹配 ERPNext Pick List purpose。 | `ask_clarification`、`validate_before_execute` |
| `customer` | `string` | `no` | - | - | - | - |
| `work_order` | `string` | `no` | - | - | - | - |
| `material_request` | `string` | `no` | - | - | - | - |
| `sales_order` | `string` | `no` | - | - | - | - |
| `parent_warehouse` | `string` | `no` | Warehouse Resolver | `warehouse` | 必须是 ERPNext Warehouse.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `locations` | `array` | `no` | 拣货明细编排 | - | array_items_schema=true、每行 qty 必须大于 0。、每行 item_code、warehouse、batch_no、serial_no、stock_uom 必须分别经 item、warehouse、batch、serial_no、uom resolver。、selection_confirmed 只能来自人工或上游策略。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |

### `erpnext.stock.list_reservations`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 Stock Reservation Entry 库存预留记录。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Stock Reservation Entry`, `Item`, `Warehouse` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `item_code`、`item_query`、`warehouse`、`voucher_type`、`voucher_no`、`status`、`limit` |

Business Contract：

- 只读查询，不创建、不提交、不取消库存预留。
- 按物料或仓库过滤时必须先解析外键。
- 按来源凭证过滤时，voucher_type 与 voucher_no 应同时提供。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `no` | Item Resolver | `item` | 必须是 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates` |
| `item_query` | `string` | `no` | 用户原话 | `item` | 仅用于解析 item_code。 | `resolve_entity`、`present_candidates` |
| `warehouse` | `string` | `no` | Warehouse Resolver | `warehouse` | 必须是 ERPNext Warehouse.name。 | `resolve_entity`、`ask_clarification` |
| `voucher_type` | `string` | `no` | 用户指定 / Runtime Context | - | 应使用 ERPNext 来源凭证类型原名。 | - |
| `voucher_no` | `string` | `no` | 用户指定 / Runtime Context | - | 必须是已存在来源凭证编号。 | - |
| `status` | `string` | `no` | - | - | - | - |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |

### `erpnext.stock.create_reservation_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Stock Reservation Entry 草稿；提交后会影响可用库存。 |
| Allowed Roles | 仓管、仓库主管 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Stock Reservation Entry`, `Item`, `Warehouse`, `UOM` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `item_code`、`item_query`、`selected_item_code`、`warehouse`、`voucher_type`、`voucher_no`、`reserved_qty`、`company`、`stock_uom` |

Business Contract：

- 创建前必须确认物料、仓库、预留数量和来源凭证。
- reserved_qty 必须大于 0，不接受“若干”等模糊数量。
- 提交预留是 L4 行为，必须另走 erpnext.stock.submit_document。
- 默认口径：voucher_type、voucher_no、voucher_detail_no 必须成组来自同一来源凭证；from_voucher_type 只作为来源迁移上下文，不得与 voucher_type 冲突。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `conditional` | Item Resolver | `item` | 必须是 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `item_query` | `string` | `conditional` | 用户原话 | `item` | 仅用于解析 item_code。 | `resolve_entity`、`present_candidates` |
| `selected_item_code` | `string` | `conditional` | Item Resolver 候选确认 | `item` | 必须来自已确认 Item 候选。 | `resolve_entity`、`present_candidates` |
| `selection_confirmed` | `boolean` | `no` | 用户确认 / Runtime Policy | - | 只有已确认候选时才能为 true。 | `ask_clarification`、`validate_before_execute` |
| `warehouse` | `string` | `True` | Warehouse Resolver | `warehouse` | 必须是 ERPNext Warehouse.name。 | `resolve_entity`、`ask_clarification` |
| `voucher_type` | `string` | `no` | - | - | - | - |
| `voucher_no` | `string` | `no` | - | - | - | - |
| `voucher_detail_no` | `string` | `no` | - | - | - | - |
| `reserved_qty` | `number` | `True` | 用户数量槽位 | - | exclusiveMinimum=0、必须大于 0。 | `ask_clarification`、`validate_before_execute` |
| `company` | `string` | `no` | Runtime Context | `company` | 必须是 ERPNext Company.name。 | `inject_context`、`resolve_entity` |
| `stock_uom` | `string` | `no` | UOM Resolver / Item 默认 | `uom` | 必须是 ERPNext UOM.name。 | `resolve_entity`、`inject_context` |
| `from_voucher_type` | `string` | `no` | - | - | - | - |

### `erpnext.stock.preview_valuation`

| 项目 | 内容 |
|---|---|
| 用途 | L1：预览库存数量和价值影响，不创建库存单据。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Item`, `Warehouse`, `Stock Ledger Entry`<br>通过 agent_bridge 预览，不写入 Stock Entry 或 Stock Reconciliation。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `items` |

Business Contract：

- 仅用于预览和决策，不代表允许创建或提交库存调整。
- items 中物料、仓库、数量、估值率必须明确；不接受模糊数量。
- 默认口径：估值预览只作风险提示，不作为财务记账真值；正式估值以 ERPNext 提交后的 Stock Ledger/GL Entry 为准。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `items` | `array` | `True` | Item/Warehouse Resolver + Slot Extractor | - | array_items_schema=true、每行 item_code、warehouse 必须分别经 item、warehouse resolver。、qty/qty_delta/required_qty 必须是明确数字。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |

### `erpnext.stock.allocate_shortages`

| 项目 | 内容 |
|---|---|
| 用途 | L1：预览库存分配与缺料，不创建预留、拣货或采购申请。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Item`, `Warehouse`, `Bin`<br>通过 agent_bridge 计算可用量和短缺量。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `items` |

Business Contract：

- 只做分配和短缺预览，不创建 Stock Reservation Entry、Pick List 或 Material Request。
- items 中 required_qty 必须明确，仓库如有指定必须解析。
- 默认口径：短缺分配优先本项目仓、其次中心仓、最后采购；保留库存不可占用，跨仓调拨必须生成独立 Stock Entry 候选。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `items` | `array` | `True` | Item/Warehouse Resolver + 需求明细 | - | array_items_schema=true、每行 item_code、warehouse 必须分别经 item、warehouse resolver。、required_qty 必须大于等于 0。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |

### `erpnext.stock.list_delivery_notes`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 Delivery Note，用于库存侧影响复核。 |
| Allowed Roles | 仓管、仓库主管、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Delivery Note` |
| Repair | `ask_clarification`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `customer`、`status`、`docstatus`、`limit` |

Business Contract：

- 只读边界工具；Delivery Note 草稿和业务流程归销售模块。
- 不允许通过该工具修改、提交或取消发货单。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `customer` | `string` | `no` | - | - | - | - |
| `status` | `string` | `no` | - | - | - | - |
| `docstatus` | `integer` | `no` | 用户选择 / Runtime Policy | - | minimum=0、maximum=2、只能是 0、1、2。 | `validate_before_execute` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |

### `erpnext.stock.list_purchase_receipts`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 Purchase Receipt，用于库存侧收货影响复核。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Purchase Receipt` |
| Repair | `ask_clarification`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `supplier`、`status`、`docstatus`、`limit` |

Business Contract：

- 只读边界工具；Purchase Receipt 草稿和采购业务流程归采购模块。
- 不允许通过该工具修改、提交或取消采购收货单。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `supplier` | `string` | `no` | - | - | - | - |
| `status` | `string` | `no` | - | - | - | - |
| `docstatus` | `integer` | `no` | 用户选择 / Runtime Policy | - | minimum=0、maximum=2、只能是 0、1、2。 | `validate_before_execute` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |

### `erpnext.stock.get_document_impact`

| 项目 | 内容 |
|---|---|
| 用途 | L0：读取 Delivery Note 或 Purchase Receipt 的库存流水影响。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Delivery Note`, `Purchase Receipt`, `Stock Ledger Entry` |
| Repair | `ask_clarification`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `doctype`、`name`、`limit` |

Business Contract：

- 只读查询，不编辑跨模块单据。
- doctype 只能是 Delivery Note 或 Purchase Receipt。
- name 必须是已存在单据编号，不能凭空编造。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `enum` | `True` | 用户指定 / Runtime Context | - | 只能是 Delivery Note 或 Purchase Receipt。 | `validate_before_execute`、`ask_clarification` |
| `name` | `string` | `True` | Document Resolver | - | 必须是已存在业务单据 name。 | `resolve_entity`、`ask_clarification` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=200 | - |

### `erpnext.stock.list_item_reorders`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 Item Reorder 行，用于查看仓库补货阈值。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Item Reorder`, `Item`, `Warehouse` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `item_code`、`item_query`、`warehouse`、`material_request_type`、`limit` |

Business Contract：

- 只读查询，不修改物料补货规则。
- 按物料或仓库过滤时必须先解析外键。
- 默认口径：material_request_type 使用 ERPNext 标准 Purchase、Material Transfer、Material Issue、Manufacture、Customer Provided；站点自定义值由元数据 resolver 读取。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `no` | Item Resolver | `item` | 必须是 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates` |
| `item_query` | `string` | `no` | 用户原话 | `item` | 仅用于解析 item_code。 | `resolve_entity`、`present_candidates` |
| `warehouse` | `string` | `no` | Warehouse Resolver | `warehouse` | 必须是 ERPNext Warehouse.name。 | `resolve_entity`、`ask_clarification` |
| `material_request_type` | `string` | `no` | - | - | - | - |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=200 | - |

### `erpnext.stock.list_quality_inspections`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询与收货、发货或过程质检相关的 Quality Inspection。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Quality Inspection`, `Item` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `item_code`、`item_query`、`reference_type`、`reference_name`、`inspection_type`、`status`、`docstatus`、`limit` |

Business Contract：

- 只读查询，不创建、不提交或修改质检单。
- 按物料过滤时必须先解析 Item。
- reference_type/reference_name 应成对出现。
- 站点配置项：inspection_type/status 的合法值必须从 Quality Inspection 元数据 options 或质量模块配置读取。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `no` | Item Resolver | `item` | 必须是 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates` |
| `item_query` | `string` | `no` | 用户原话 | `item` | 仅用于解析 item_code。 | `resolve_entity`、`present_candidates` |
| `reference_type` | `string` | `no` | - | - | - | - |
| `reference_name` | `string` | `no` | - | - | - | - |
| `inspection_type` | `string` | `no` | - | - | - | - |
| `status` | `string` | `no` | - | - | - | - |
| `docstatus` | `integer` | `no` | 用户选择 / Runtime Policy | - | minimum=0、maximum=2、只能是 0、1、2。 | `validate_before_execute` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=100 | - |

### `erpnext.stock.create_quality_inspection_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Quality Inspection 草稿；不提交。 |
| Allowed Roles | 仓管、仓库主管 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Quality Inspection`, `Quality Inspection Reading`, `Item` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `item_code`、`item_query`、`selected_item_code`、`inspection_type`、`reference_type`、`reference_name`、`sample_size`、`report_date`、`status`、`readings` |

Business Contract：

- 创建前必须确认物料、质检类型、来源单据和抽样数量。
- item_code 必须来自 Item Resolver 或已确认 selected_item_code。
- readings 不得由模型臆造检测值；必须来自用户输入、设备结果或受控表单。
- 站点配置项：不同 inspection_type 的必填字段、合格状态和提交流程必须从质量模块元数据、模板和 Workflow 读取。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `conditional` | Item Resolver | `item` | 必须是 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `item_query` | `string` | `conditional` | 用户原话 | `item` | 仅用于解析 item_code。 | `resolve_entity`、`present_candidates` |
| `selected_item_code` | `string` | `conditional` | Item Resolver 候选确认 | `item` | 必须来自已确认 Item 候选。 | `resolve_entity`、`present_candidates` |
| `selection_confirmed` | `boolean` | `no` | 用户确认 / Runtime Policy | - | 只有已确认候选时才能为 true。 | `ask_clarification`、`validate_before_execute` |
| `inspection_type` | `string` | `no` | - | - | - | - |
| `reference_type` | `string` | `no` | - | - | - | - |
| `reference_name` | `string` | `no` | - | - | - | - |
| `sample_size` | `number` | `no` | 用户数量槽位 | - | minimum=0、必须大于等于 0。 | `ask_clarification`、`validate_before_execute` |
| `inspected_by` | `string` | `no` | - | - | - | - |
| `verified_by` | `string` | `no` | - | - | - | - |
| `report_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。 | `ask_clarification`、`inject_context` |
| `status` | `string` | `no` | - | - | - | - |
| `remarks` | `string` | `no` | - | - | - | - |
| `readings` | `array` | `no` | 质检结果表单 / 设备数据 | - | array_items_schema=true、检测值必须来自可追溯来源，不允许模型臆造。 | `ask_clarification`、`validate_before_execute` |

### `erpnext.stock.verify_purchase_receipt_stock_impact`

| 项目 | 内容 |
|---|---|
| 用途 | L0：核对已提交 Purchase Receipt 的库存流水和收货数量/价值影响。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Purchase Receipt`, `Stock Ledger Entry`, `Item`, `Warehouse` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `purchase_receipt`、`item_code`、`warehouse`、`limit` |

Business Contract：

- 只读校验，不修改 Purchase Receipt 或库存流水。
- purchase_receipt 必须是已存在的采购收货单编号。
- 按物料或仓库过滤时必须先解析外键。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `purchase_receipt` | `string` | `True` | Document Resolver | - | 必须是已存在 Purchase Receipt.name。 | `resolve_entity`、`ask_clarification` |
| `item_code` | `string` | `no` | Item Resolver | `item` | 必须是 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates` |
| `warehouse` | `string` | `no` | Warehouse Resolver | `warehouse` | 必须是 ERPNext Warehouse.name。 | `resolve_entity`、`ask_clarification` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=500 | - |

### `erpnext.stock.get_item_lifecycle_summary`

| 项目 | 内容 |
|---|---|
| 用途 | L0：汇总物料在采购收货、库存流水、质检、库存移动和采购发票中的生命周期。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Item`, `Purchase Receipt Item`, `Stock Ledger Entry`, `Quality Inspection`, `Stock Entry Detail`, `Purchase Invoice Item`, `Warehouse` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `item_code`、`item_query`、`selected_item_code`、`project`、`warehouse`、`from_date`、`to_date`、`limit` |

Business Contract：

- 只读汇总，不修改任何生命周期相关单据。
- 必须先解析到唯一 Item；日期范围必须是 ISO 日期。
- warehouse 如指定必须解析为 Warehouse.name。
- 默认口径：project 必须通过 Project resolver 精确命中，并受当前 ERPNext 用户对项目和目标单据的权限共同限制。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `conditional` | Item Resolver | `item` | 必须是 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `item_query` | `string` | `conditional` | 用户原话 | `item` | 仅用于解析 item_code。 | `resolve_entity`、`present_candidates` |
| `selected_item_code` | `string` | `conditional` | Item Resolver 候选确认 | `item` | 必须来自已确认 Item 候选。 | `resolve_entity`、`present_candidates` |
| `selection_confirmed` | `boolean` | `no` | 用户确认 / Runtime Policy | - | 只有已确认候选时才能为 true。 | `ask_clarification`、`validate_before_execute` |
| `project` | `string` | `no` | - | - | - | - |
| `warehouse` | `string` | `no` | Warehouse Resolver | `warehouse` | 必须是 ERPNext Warehouse.name。 | `resolve_entity`、`ask_clarification` |
| `from_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。 | `ask_clarification` |
| `to_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期，且不早于 from_date。 | `ask_clarification`、`validate_before_execute` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=200 | - |

### `erpnext.stock.list_warehouses`

| 项目 | 内容 |
|---|---|
| 用途 | L0：按公司或名称关键字查询 Warehouse 主数据。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Warehouse`, `Company` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `company`、`query`、`limit` |

Business Contract：

- 只读查询，不创建或修改仓库。
- company 如指定必须解析成 ERPNext Company.name。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `company` | `string` | `no` | Company Resolver / Runtime Context | `company` | 必须是 ERPNext Company.name。 | `resolve_entity`、`inject_context` |
| `query` | `string` | `no` | 用户原话 | `warehouse` | 仅作为 Warehouse 候选检索词。 | `resolve_entity`、`present_candidates` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=200 | - |

### `erpnext.stock.create_warehouse`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Warehouse 主数据；不移动库存。 |
| Allowed Roles | 仓库主管 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Warehouse`, `Company` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `data` |

Business Contract：

- 仅仓库主管可创建仓库主数据。
- data.company、data.parent_warehouse 如存在必须分别经 company、warehouse resolver。
- 不得凭空创建与项目/公司不匹配的仓库。
- 默认口径：仓库按公司缩写后缀和父级树创建；group warehouse 只作父级不参与库存交易，默认账户从公司或父仓配置继承。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | Warehouse 表单编排 | `warehouse` | 必须包含明确仓库名称和公司上下文。、涉及 company/parent_warehouse 时必须先解析。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |

### `erpnext.stock.update_warehouse`

| 项目 | 内容 |
|---|---|
| 用途 | L3：更新 Warehouse 主数据；不移动库存。 |
| Allowed Roles | 仓库主管 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Warehouse`, `Company` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `name`、`data` |

Business Contract：

- 仅仓库主管可更新仓库主数据。
- name 必须解析为现有 Warehouse.name。
- data.company、data.parent_warehouse 如存在必须分别经 company、warehouse resolver。
- 制度配置项：有库存或历史流水的 Warehouse 禁止修改 name、company、is_group 等关键字段；仅允许修改展示、联系人和自定义字段并保留审计。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `name` | `string` | `True` | Warehouse Resolver | `warehouse` | 必须是已存在的 ERPNext Warehouse.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `data` | `object` | `True` | Warehouse 变更表单 | - | 只能包含允许变更的 Warehouse 字段。、涉及 company/parent_warehouse 时必须先解析。 | `resolve_entity`、`ask_clarification`、`validate_before_execute` |

### `erpnext.stock.list_item_groups`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 Item Group 主数据。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Item Group` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `query`、`parent_item_group`、`is_group`、`filters`、`fields`、`limit`、`offset`、`order_by` |

Business Contract：

- 只读查询，不创建或修改物料组。
- parent_item_group 如指定必须解析到 Item Group.name。
- filters、fields、order_by 应由 Runtime 控制，避免模型直接拼接任意过滤。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `query` | `string` | `no` | 用户原话 | `item_group` | 仅作为 Item Group 候选检索词。 | `resolve_entity`、`present_candidates` |
| `parent_item_group` | `string` | `no` | Item Group Resolver | `item_group` | 必须是 ERPNext Item Group.name。 | `resolve_entity`、`present_candidates` |
| `is_group` | `boolean` | `no` | - | - | - | - |
| `filters` | `object` | `no` | Runtime Builder | - | 应由 Runtime 构造，避免模型直接拼 Frappe filter。 | `validate_before_execute` |
| `fields` | `array` | `no` | Runtime Builder | - | array_items_schema=true、只允许读取安全展示字段。 | `validate_before_execute` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=200 | - |
| `offset` | `integer` | `no` | - | - | minimum=0 | - |
| `order_by` | `string` | `no` | - | - | - | - |

### `erpnext.stock.create_item_group`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 Item Group 主数据；不创建物料、不移动库存。 |
| Allowed Roles | 仓库主管 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Item Group` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `data` |

Business Contract：

- 仅仓库主管可创建物料组主数据。
- data.parent_item_group 如存在必须经 item_group resolver。
- 默认口径：物料组树遵循物料治理规则；is_group=true 仅作分类父级，实际 Item 必须挂到叶子物料组。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | Item Group 表单编排 | `item_group` | 必须包含明确物料组名称。、涉及 parent_item_group 时必须解析到 Item Group.name。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |

### `erpnext.stock.update_item_group`

| 项目 | 内容 |
|---|---|
| 用途 | L3：更新 Item Group 主数据；不创建物料、不移动库存。 |
| Allowed Roles | 仓库主管 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Item Group` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `name`、`data` |

Business Contract：

- 仅仓库主管可更新物料组主数据。
- name 必须解析为现有 Item Group.name。
- data.parent_item_group 如存在必须经 item_group resolver。
- 制度配置项：已有物料挂载的 Item Group 禁止随意修改 is_group 和父级；如需调整分类必须先做影响预览并由管理员确认。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `name` | `string` | `True` | Item Group Resolver | `item_group` | 必须是已存在的 ERPNext Item Group.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `data` | `object` | `True` | Item Group 变更表单 | - | 只能包含允许变更的 Item Group 字段。、涉及 parent_item_group 时必须先解析。 | `resolve_entity`、`ask_clarification`、`validate_before_execute` |

### `erpnext.stock.list_uoms`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询 UOM 主数据。 |
| Allowed Roles | 仓管、仓库主管、采购、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `UOM` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `query`、`enabled`、`filters`、`fields`、`limit`、`offset`、`order_by` |

Business Contract：

- 只读查询，不创建或修改 UOM。
- query 只能作为 UOM 候选检索词。
- filters、fields、order_by 应由 Runtime 控制，避免模型直接拼接任意过滤。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `query` | `string` | `no` | 用户原话 | `uom` | 仅作为 UOM 候选检索词。 | `resolve_entity`、`present_candidates` |
| `enabled` | `boolean` | `no` | - | - | - | - |
| `filters` | `object` | `no` | Runtime Builder | - | 应由 Runtime 构造，避免模型直接拼 Frappe filter。 | `validate_before_execute` |
| `fields` | `array` | `no` | Runtime Builder | - | array_items_schema=true、只允许读取安全展示字段。 | `validate_before_execute` |
| `limit` | `integer` | `no` | - | - | minimum=1、maximum=200 | - |
| `offset` | `integer` | `no` | - | - | minimum=0 | - |
| `order_by` | `string` | `no` | - | - | - | - |

### `erpnext.stock.create_uom`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建 UOM 主数据；不影响既有库存余额。 |
| Allowed Roles | 仓库主管 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `UOM` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `data` |

Business Contract：

- 仅仓库主管可创建 UOM 主数据。
- 创建前必须确认 UOM 名称、启用状态和是否允许小数。
- 默认口径：UOM 使用标准中文名或行业通用符号；是否允许小数由 must_be_whole_number 控制，换算关系通过 UOM Conversion Detail 维护。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `data` | `object` | `True` | UOM 表单编排 | `uom` | 必须包含明确 UOM 名称。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |

### `erpnext.stock.update_uom`

| 项目 | 内容 |
|---|---|
| 用途 | L3：更新 UOM 主数据；不直接影响既有库存余额。 |
| Allowed Roles | 仓库主管 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `UOM` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `name`、`data` |

Business Contract：

- 仅仓库主管可更新 UOM 主数据。
- name 必须解析为现有 UOM.name。
- 制度配置项：已有库存或交易引用的 UOM 不修改名称和小数策略；需要变化时新增替代 UOM 并维护换算关系。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `name` | `string` | `True` | UOM Resolver | `uom` | 必须是已存在的 ERPNext UOM.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `data` | `object` | `True` | UOM 变更表单 | - | 只能包含允许变更的 UOM 字段。 | `ask_clarification`、`validate_before_execute` |

### `erpnext.stock.submit_document`

| 项目 | 内容 |
|---|---|
| 用途 | L4：提交库存相关单据，可能改变库存、预留或单据状态。 |
| Allowed Roles | 仓库主管 |
| Expose | `agent_visible` |
| Confirm | `submit_confirm` |
| Backend Mapping | DocType: `Stock Entry`, `Stock Reconciliation`, `Delivery Note`, `Purchase Receipt`, `Pick List`, `Stock Reservation Entry` |
| Repair | `resolve_entity`、`ask_clarification`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `doctype`、`name`、`confirmation` |

Business Contract：

- 必须有明确 confirmation，包含确认人、时间、原因和确认文本。
- 只能提交 schema 枚举中的库存相关单据。
- Stock Reconciliation、数量调整类 Stock Entry 或影响账面库存的提交必须具备主管审批依据。
- 不得用该工具绕过采购、销售或项目模块对源单据草稿的业务流程。
- 默认口径：库存模块默认只允许提交 Stock Entry 和 Purchase Receipt；Delivery Note 提交属于销售/仓配边界，需单独授予角色策略后才暴露。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `enum` | `True` | Document Type Resolver | - | 只能是 Stock Entry、Stock Reconciliation、Delivery Note、Purchase Receipt、Pick List、Stock Reservation Entry。 | `validate_before_execute`、`ask_clarification` |
| `name` | `string` | `True` | Document Resolver | - | 必须是已存在且处于可提交状态的单据 name。 | `resolve_entity`、`ask_clarification`、`validate_before_execute` |
| `confirmation` | `object` | `True` | Confirmation Gate | - | 必须包含 confirmed_by、confirmed_at、confirmation_text 和 reason。、库存盘点/数量调整提交应包含 supervisor approval_reference。 | `ask_clarification`、`validate_before_execute`、`permission_denied` |

### `erpnext.projects.get_project_cost_context`

| 项目 | 内容 |
|---|---|
| 用途 | L0：读取项目成本上下文，汇总 Project、Task、Stock Entry 和 Purchase Receipt 相关记录。 |
| Allowed Roles | 项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Project`, `Task`, `Stock Entry`, `Purchase Receipt` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `project`、`company`、`from_date`、`to_date`、`include_tasks`、`include_stock_entries`、`include_purchase_receipts`、`limit` |

Business Contract：

- 只读取项目成本上下文，不创建采购、库存或项目单据。
- 日期范围用于过滤 posting_date；未提供日期时按 Runtime 默认 limit 控制返回量。
- 默认口径：v0.1 项目成本先纳入带 project/cost_center 的 Stock Entry、Purchase Receipt 和 Purchase Invoice；Timesheet、Expense Claim、Sales Invoice 作为 v0.2 扩展口径。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `project` | `string` | `True` | Project Resolver | `project` | 必须是已存在的 ERPNext Project.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `company` | `string` | `no` | Runtime Context / Company Resolver | `company` | 如填写，必须是已存在的 ERPNext Company.name。 | - |
| `from_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。 | - |
| `to_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。 | - |
| `include_tasks` | `boolean` | `no` | Runtime 默认值 / 用户选择 | - | - | - |
| `include_stock_entries` | `boolean` | `no` | Runtime 默认值 / 用户选择 | - | - | - |
| `include_purchase_receipts` | `boolean` | `no` | Runtime 默认值 / 用户选择 | - | - | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100 | - |

### `erpnext.projects.get_material_issue_context`

| 项目 | 内容 |
|---|---|
| 用途 | L0/L1：预览项目领料需求与源仓库存可用量，不创建 Stock Entry。 |
| Allowed Roles | 项目经理、班组长 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Project`, `Bin`, `Item`, `Warehouse`<br>读取 Project 并通过库存余额接口检查源仓可用量。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `project`、`source_warehouse`、`items` |

Business Contract：

- 仅做领料预览，不创建或提交库存移动。
- items 每行必须有正数 qty；item_code 缺失时必须通过 item_query/selected_item_code 解析并确认。
- 有缺料时必须展示 shortages，不得默认创建负库存草稿。
- 默认口径：可用库存等于实际库存减保留库存和质量冻结库存；批次/序列号受控物料必须按对应维度进一步过滤。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `project` | `string` | `True` | Project Resolver | `project` | 必须是已存在的 ERPNext Project.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `source_warehouse` | `string` | `True` | Warehouse Resolver | `warehouse` | 必须是已存在的 ERPNext Warehouse.name 全称。、禁止把中心仓、项目仓等简称直接写入 ToolCall。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `items` | `array` | `True` | Item Resolver + 项目领料表单编排 | `item` | array_items_schema=true、数组至少 1 行。、每行 qty 必须大于 0。、每行 item_code 必须是已存在的 ERPNext Item.item_code；如使用 selected_item_code，必须 selection_confirmed=true。、每行 cost_center 如填写，必须是已存在的 ERPNext Cost Center.name。、每行 task 如填写，必须属于当前 project 或由项目上下文确认。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |

### `erpnext.projects.create_material_issue_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建项目领料 Stock Entry 草稿，写入项目和成本中心上下文；不提交库存移动。 |
| Allowed Roles | 项目经理、班组长 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Project`, `Stock Entry`, `Stock Entry Detail`, `Item`, `Warehouse`, `Cost Center`<br>Method: `ERPNextClient.create_stock_entry_draft` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `project`、`source_warehouse`、`company`、`posting_date`、`posting_time`、`cost_center`、`expense_account`、`require_available_stock`、`items`、`remarks` |

Business Contract：

- 创建前必须确认项目、源仓、物料、数量、成本中心、费用科目和备注。
- 默认 require_available_stock=true；存在缺料时不得创建草稿，除非用户明确允许并完成风险确认。
- 该工具只创建 Stock Entry 草稿，不提交；提交仍由库存/项目相关提交工具处理。
- items 每行 item_code、source_warehouse、project、cost_center 必须使用 resolver 后的 ERPNext 主键。
- 默认口径：项目领料成本中心优先取项目成本中心，费用科目从 Item/Company 默认账户解析；默认禁止负库存，除非站点允许且用户完成风险确认。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `project` | `string` | `True` | Project Resolver | `project` | 必须是已存在的 ERPNext Project.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `source_warehouse` | `string` | `True` | Warehouse Resolver | `warehouse` | 必须是已存在的 ERPNext Warehouse.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `company` | `string` | `no` | Runtime Context / Company Resolver | `company` | 如填写，必须是已存在的 ERPNext Company.name。 | - |
| `posting_date` | `string` | `no` | Date Resolver | `date` | 必须是 ISO 日期。 | - |
| `posting_time` | `string` | `no` | Runtime / 用户选择 | - | 如填写，必须是 ERPNext 接受的时间格式。 | - |
| `cost_center` | `string` | `no` | Cost Center Resolver / Project 默认值 | `cost_center` | 如填写，必须是已存在的 ERPNext Cost Center.name。 | - |
| `expense_account` | `string` | `no` | Account Resolver / Runtime Context | `account` | 如填写，必须是当前公司可用的费用科目。 | - |
| `remarks` | `string` | `no` | 用户确认文本 / Runtime 默认值 | - | 必须能说明项目领料原因或用途。 | - |
| `require_available_stock` | `boolean` | `no` | Runtime 默认值 / 用户确认 | - | 默认 true。 | - |
| `items` | `array` | `True` | Item Resolver + 项目领料表单编排 | `item` | array_items_schema=true、数组至少 1 行。、每行 qty 必须大于 0。、每行 item_code 必须是已存在的 ERPNext Item.item_code；如使用 selected_item_code，必须 selection_confirmed=true。、每行 cost_center 如填写，必须是已存在的 ERPNext Cost Center.name。、每行 task 如填写，必须属于当前 project 或由项目上下文确认。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |

### `erpnext.projects.verify_material_issue_cost_impact`

| 项目 | 内容 |
|---|---|
| 用途 | L0：读取已创建或已提交的项目 Material Issue Stock Entry，核对项目成本行和库存台账影响。 |
| Allowed Roles | 项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Stock Entry`, `Stock Entry Detail`, `Stock Ledger Entry`, `Project` |
| Repair | `resolve_entity`、`ask_clarification`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `stock_entry`、`project`、`limit` |

Business Contract：

- 只读取并校验项目领料成本影响，不修改库存或项目成本。
- 如果 Stock Entry 未提交，必须提示成本和库存台账影响可能不是最终结果。
- project 如填写，只核对匹配该项目的 Stock Entry item 行。
- 默认口径：项目成本归集优先使用明细行 project，其次单据 project，成本中心作为辅助维度和财务核对依据。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `stock_entry` | `string` | `True` | Document Resolver | `docname` | 必须是已存在的 ERPNext Stock Entry.name。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `project` | `string` | `no` | Project Resolver | `project` | 如填写，必须是已存在的 ERPNext Project.name。 | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=500 | - |

### `erpnext.create_todo`

| 项目 | 内容 |
|---|---|
| 用途 | L2：创建跟进任务。 |
| Allowed Roles | 仓管、采购、项目经理、班组长、财务、资产管理员、管理层、系统管理员 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `ToDo` |
| Repair | `ask_clarification`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `description`、`allocated_to`、`reference_type`、`reference_name`、`date` |

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `description` | `string` | `True` | 用户确认文本 | - | - | - |
| `allocated_to` | `string` | `no` | User Resolver / 当前用户 | `user` | - | - |
| `priority` | `string` | `no` | - | - | - | - |
| `reference_type` | `string` | `no` | DocType Resolver | `doctype` | - | - |
| `reference_name` | `string` | `no` | Document Resolver | `docname` | - | - |
| `date` | `string` | `no` | Date Resolver | `date` | - | - |

### `erpnext.add_comment`

| 项目 | 内容 |
|---|---|
| 用途 | L2：给 ERPNext 单据添加评论。 |
| Allowed Roles | 仓管、采购、项目经理、班组长、财务、资产管理员、管理层、系统管理员 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Comment`<br>Method: `frappe.desk.form.utils.add_comment` |
| Repair | `resolve_entity`、`ask_clarification`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `reference_doctype`、`reference_name`、`content` |

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `reference_doctype` | `string` | `True` | - | `doctype` | - | - |
| `reference_name` | `string` | `True` | - | `docname` | - | - |
| `content` | `string` | `True` | 用户确认文本 | - | - | - |
| `comment_email` | `string` | `no` | - | - | - | - |
| `comment_by` | `string` | `no` | - | - | - | - |

### `erpnext.assign_to`

| 项目 | 内容 |
|---|---|
| 用途 | L2：把 ERPNext 单据分配给一个或多个用户。 |
| Allowed Roles | 仓管、采购、项目经理、班组长、财务、资产管理员、管理层、系统管理员 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `ToDo`<br>Method: `frappe.desk.form.assign_to.add` |
| Repair | `resolve_entity`、`ask_clarification`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `doctype`、`name`、`assign_to`、`description`、`date` |

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `string` | `True` | - | `doctype` | - | - |
| `name` | `string` | `True` | - | `docname` | - | - |
| `assign_to` | `array` | `True` | - | `user` | array_items_schema=true | - |
| `description` | `string` | `no` | - | - | - | - |
| `priority` | `string` | `no` | - | - | - | - |
| `date` | `string` | `no` | - | `date` | - | - |

### `erpnext.delete_attachment`

| 项目 | 内容 |
|---|---|
| 用途 | L4：删除一个 ERPNext File 附件。 |
| Allowed Roles | 仓管、采购、项目经理、班组长、财务、资产管理员、系统管理员 |
| Expose | `agent_visible` |
| Confirm | `submit_confirm` |
| Backend Mapping | DocType: `File` |
| Repair | `resolve_entity`、`permission_denied`、`erpnext_validation_error` |
| 审计重点 | `file_name` |

Business Contract：

- 删除附件必须展示文件名和关联单据并获得确认。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `file_name` | `string` | `True` | - | `file` | - | - |

### `erpnext.call_method`

| 项目 | 内容 |
|---|---|
| 用途 | L1：调用已白名单允许的 Frappe 方法；有专用 ToolCall 时禁止直接使用。 |
| Allowed Roles | developer |
| Expose | `developer_only` |
| Confirm | `user_confirm` |
| Backend Mapping | Method: `任意已允许 Frappe Method` |
| Repair | `permission_denied`、`validate_before_execute`、`erpnext_validation_error` |
| 审计重点 | `method`、`args`、`http_method`、`confirmation` |

Business Contract：

- 员工 Agent 永不直接使用该工具。
- 业务动作必须优先沉淀为专用 ToolCall。
- method 必须在 Adapter/后端白名单范围内。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `method` | `string` | `True` | Developer | - | 必须是允许调用的 Frappe 方法。 | - |
| `args` | `object` | `no` | Developer | - | 参数结构必须进入审计日志。 | - |
| `http_method` | `enum` | `no` | Developer | - | 只允许 GET 或 POST。 | - |
| `confirmation` | `object` | `no` | - | - | - | - |

### `erpnext.buying.search_suppliers`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询供应商主数据，用于采购寻源、下单前校验和候选展示。 |
| Allowed Roles | 采购、仓管、项目经理、班组长、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Supplier`<br>Method: `search_documents`<br>只读 Supplier 安全字段，按名称、分组、类型和冻结/禁用状态过滤。 |
| Repair | `resolve_entity`、`present_candidates`、`ask_clarification`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `query`、`supplier_group`、`supplier_type`、`disabled`、`is_frozen`、`on_hold`、`limit` |

Business Contract：

- 只允许读取供应商候选和采购拦截标记，不创建、不修改供应商。
- query 仅作为检索词；命中多个供应商时必须展示候选，不允许模型擅自选择。
- on_hold、is_frozen、prevent_rfqs、prevent_pos 等字段只能作为后续采购决策依据，不能在本工具中改写。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `query` | `string` | `no` | 用户原话 | - | 仅作为 Supplier.supplier_name 模糊检索输入。 | - |
| `supplier_group` | `string` | `no` | Supplier Group Resolver | `supplier_group` | 必须是 ERPNext Supplier Group.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `supplier_type` | `string` | `no` | 用户选择 / ERPNext 枚举 | - | 必须传 ERPNext 可接受的 Supplier Type 值。 | - |
| `disabled` | `boolean` | `no` | - | - | - | - |
| `is_frozen` | `boolean` | `no` | - | - | - | - |
| `on_hold` | `boolean` | `no` | - | - | - | - |
| `fields` | `array` | `no` | - | - | array_items_schema=true | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100、不得超过 schema 上限。 | - |

### `erpnext.buying.search_supplier_scorecards`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询供应商评分卡和 RFQ/PO 警告或阻止标记。 |
| Allowed Roles | 采购、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Supplier Scorecard`<br>Method: `search_documents` |
| Repair | `resolve_entity`、`present_candidates`、`ask_clarification`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `supplier`、`status`、`limit`、`offset`、`order_by` |

Business Contract：

- 只读评分卡，不改变供应商状态或采购限制。
- supplier 缺失时可作为列表查询；supplier 存在时必须解析为真实 Supplier.name。
- 评分卡中的 warn/prevent 标记必须在创建 RFQ/PO 草稿前作为风险提示。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `supplier` | `string` | `conditional` | Supplier Resolver | `supplier` | 必须是 ERPNext Supplier.name 全称。、不得直接使用用户简称作为主键。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `status` | `string` | `no` | 用户选择 / ERPNext 状态 | - | 站点配置项：Supplier Scorecard status 的合法枚举必须从当前 ERPNext 元数据或报表返回值读取。 | - |
| `fields` | `array` | `no` | - | - | array_items_schema=true | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100、不得超过 schema 上限。 | - |
| `offset` | `integer` | `no` | - | - | minimum=0 | - |
| `order_by` | `string` | `no` | - | - | - | - |

### `erpnext.buying.get_supplier_procurement_profile`

| 项目 | 内容 |
|---|---|
| 用途 | L1：汇总供应商、评分卡、物料供应商和采购价格上下文，供 RFQ/PO 前置判断。 |
| Allowed Roles | 采购、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Supplier`, `Supplier Scorecard`, `Item Supplier`, `Item Price`<br>Method: `get_document`, `search_documents` |
| Repair | `resolve_entity`、`present_candidates`、`ask_clarification`、`inject_context`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `supplier`、`company`、`item_code`、`currency`、`price_list`、`scorecard_limit` |

Business Contract：

- 只读采购资格预览，不创建 RFQ、PO 或价格。
- supplier 必须唯一解析；如果供应商被禁用、冻结、on hold 或存在 prevent 标记，后续创建类工具必须提示风险或阻止。
- item_code 可选；提供后必须先解析成真实 Item.item_code，再读取 Item Supplier 和 Item Price。
- 默认口径：company 用于上下文、审计和跨公司隔离；只有当目标 DocType/报表存在 company 字段时才参与价格或资格过滤。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `supplier` | `string` | `True` | Supplier Resolver | `supplier` | 必须是 ERPNext Supplier.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `company` | `string` | `conditional` | Runtime Context | `company` | 必须是 ERPNext Company.name 全称。、模型不应猜公司名。 | `inject_context`、`resolve_entity`、`ask_clarification` |
| `item_code` | `string` | `conditional` | Item Resolver | `item` | 必须是已存在、未禁用的 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `currency` | `string` | `no` | - | - | - | - |
| `price_list` | `string` | `no` | Buying Price List Resolver / 用户选择 | - | 默认口径：价格表必须通过 Price List resolver 精确命中且 buying=1；无匹配时不填价格表并提示用户选择。 | - |
| `scorecard_limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=20、建议保持较小值，仅用于最近评分卡上下文。 | - |

### `erpnext.buying.create_supplier_group_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建供应商分组主数据草稿/记录。 |
| Allowed Roles | 采购、管理层 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Supplier Group`<br>Method: `create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `supplier_group_name`、`parent_supplier_group`、`is_group` |

Business Contract：

- 创建前必须确认分组名称、上级分组和是否为 group。
- 不得用自然语言简称直接写 parent_supplier_group，必须解析为 ERPNext Supplier Group.name。
- 默认口径：Supplier Group 通过 resolver 精确命中；新建分组默认挂到站点根供应商组，命名冲突交由 ERPNext 唯一性校验拦截。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `supplier_group_name` | `string` | `True` | 用户确认 | - | 必须是用户确认的新分组名称。、创建前建议先搜索同名或近似分组。 | `ask_clarification`、`present_candidates` |
| `parent_supplier_group` | `string` | `conditional` | Supplier Group Resolver | `supplier_group` | 必须是 ERPNext Supplier Group.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `is_group` | `boolean` | `no` | 用户选择 / Runtime 默认 | - | 默认值待 ERPNext 后端处理；用户明确指定时必须保留。 | - |

### `erpnext.buying.create_supplier_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建供应商主数据草稿/记录，不提交采购交易。 |
| Allowed Roles | 采购、管理层 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Supplier`<br>Method: `create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `supplier_name`、`supplier_group`、`supplier_type`、`country`、`tax_id`、`default_currency` |

Business Contract：

- 创建前必须确认供应商名称、分组、类型和必要税务/币种信息。
- 创建供应商主数据不代表采购准入通过，也不会创建 RFQ/PO。
- 创建前建议先调用 search_suppliers 检查重名或近似供应商。
- 默认口径：供应商最小字段从 Supplier 元数据读取；tax_id 如存在唯一策略必须前置查重，准入审批交给 ERPNext Workflow/权限控制。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `supplier_name` | `string` | `True` | 用户确认 | - | 必须是用户确认的新供应商名称。、不得用模型猜测或补全法人名称。 | `ask_clarification`、`present_candidates` |
| `supplier_group` | `string` | `conditional` | Supplier Group Resolver | `supplier_group` | 必须是 ERPNext Supplier Group.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `supplier_type` | `string` | `no` | 用户选择 / ERPNext 默认 | - | 站点配置项：合法 Supplier Type 必须从 Supplier 元数据 options 或站点供应商类型字典读取。 | - |
| `country` | `string` | `no` | - | - | - | - |
| `tax_id` | `string` | `no` | - | - | - | - |
| `default_currency` | `string` | `no` | Currency Resolver / 用户确认 | - | 默认口径：默认币种非必填；缺省使用公司默认币种，跨币种采购必须由用户明确确认。 | - |

### `erpnext.buying.create_material_request_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建采购类材料申请草稿，不提交。 |
| Allowed Roles | 采购、项目经理、班组长 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Material Request`, `Material Request Item`<br>Method: `create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `company`、`material_request_type`、`schedule_date`、`items` |

Business Contract：

- 创建前必须确认物料、数量、需求日期、目标仓库或项目归属。
- items 至少 1 行；每行必须有真实 item_code 或已确认 selected_item_code。
- 数量必须是正数，不能接受一批、若干等模糊数量。
- 项目采购或项目领用场景必须带 project 或能从当前员工上下文注入。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `material_request_type` | `string` | `no` | Runtime 默认 / 用户选择 | - | 建议限定在 ERPNext 合法 Material Request Type。 | - |
| `schedule_date` | `string` | `conditional` | Date Resolver | `date` | 必须是 ISO 日期。 | `ask_clarification`、`inject_context` |
| `company` | `string` | `conditional` | Runtime Context | `company` | 必须是 ERPNext Company.name 全称。、模型不应猜公司名。 | `inject_context`、`resolve_entity` |
| `items` | `array` | `True` | Item Resolver + Slot Extractor | `item` | array_items_schema=true、数组至少 1 行。、每行 qty 必须大于 0。、每行 item_code 必须来自 Item Resolver。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `items[].item_code` | `nested` | `conditional` | Item Resolver | `item` | 外键：必须是已存在、未禁用的 ERPNext Item.item_code。 | - |
| `items[].schedule_date` | `nested` | `conditional` | Date Resolver | `date` | 行级日期缺省时可继承顶层 schedule_date。 | - |
| `items[].warehouse` | `nested` | `conditional` | Warehouse Resolver / 员工默认仓库 | `warehouse` | 必须是 ERPNext Warehouse.name 全称。、禁止把中心仓、项目仓等简称直接写入 ToolCall。 | - |

### `erpnext.buying.create_request_for_quotation_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建询价单草稿，包含已解析供应商和物料行，不提交。 |
| Allowed Roles | 采购 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Request for Quotation`, `Request for Quotation Supplier`, `Request for Quotation Item`<br>Method: `create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `transaction_date`、`schedule_date`、`company`、`suppliers`、`items`、`message_for_supplier` |

Business Contract：

- 创建前必须确认至少一个供应商和至少一个物料行。
- 供应商必须解析为真实 Supplier.name；命中多个供应商时必须展示候选。
- 创建 RFQ 草稿不代表发出询价；提交需另走 buying.submit_document。
- 实现约定：RFQ 创建工具应把 company 与 message_for_supplier 写入 payload；补映射前 Runtime 不依赖这两个字段落库。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `transaction_date` | `string` | `conditional` | Date Resolver | `date` | 必须是 ISO 日期。 | - |
| `schedule_date` | `string` | `conditional` | Date Resolver | `date` | 必须是 ISO 日期。 | - |
| `company` | `string` | `conditional` | Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `message_for_supplier` | `string` | `no` | - | - | - | - |
| `suppliers` | `array` | `True` | Supplier Resolver | `supplier` | array_items_schema=true、数组至少 1 行。、每个 supplier 必须是 ERPNext Supplier.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `items` | `array` | `True` | Item Resolver + Slot Extractor | `item` | array_items_schema=true、数组至少 1 行。、每行 qty 必须大于 0。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `items[].item_code` | `nested` | `conditional` | Item Resolver | `item` | 必须是已存在、未禁用的 ERPNext Item.item_code。 | - |
| `items[].schedule_date` | `nested` | `conditional` | Date Resolver | `date` | 行级日期缺省时可继承顶层 schedule_date。 | - |
| `items[].warehouse` | `nested` | `conditional` | Warehouse Resolver | `warehouse` | 如填写，必须是 ERPNext Warehouse.name 全称。 | - |

### `erpnext.buying.create_supplier_quotation_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建供应商报价单草稿，不提交。 |
| Allowed Roles | 采购 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Supplier Quotation`, `Supplier Quotation Item`<br>Method: `create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `supplier`、`transaction_date`、`valid_till`、`company`、`currency`、`buying_price_list`、`items` |

Business Contract：

- 创建前必须确认供应商、报价物料、数量、价格和有效期。
- supplier 必须解析为真实 Supplier.name，不允许直接使用用户简称。
- 报价单草稿不代表采纳报价；比较或转订单需后续独立工具和确认。
- 实现约定：Supplier Quotation 草稿工具应把 company 与 buying_price_list 写入 payload；补映射前 Runtime 只把它们作为确认摘要和后续修正依据。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `supplier` | `string` | `True` | Supplier Resolver | `supplier` | 必须是 ERPNext Supplier.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `transaction_date` | `string` | `conditional` | Date Resolver | `date` | 必须是 ISO 日期。 | - |
| `valid_till` | `string` | `conditional` | Date Resolver | `date` | 必须是 ISO 日期。、默认口径：valid_till 必须不早于 transaction_date；早于交易日期时追问或拒绝生成草稿。 | - |
| `company` | `string` | `conditional` | Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `currency` | `string` | `no` | - | - | - | - |
| `buying_price_list` | `string` | `no` | - | - | - | - |
| `items` | `array` | `True` | Item Resolver + Slot Extractor | `item` | array_items_schema=true、数组至少 1 行。、每行 qty 必须大于 0，rate 或 price_list_rate 不得为负。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `items[].item_code` | `nested` | `conditional` | Item Resolver | `item` | 必须是已存在、未禁用的 ERPNext Item.item_code。 | - |
| `items[].warehouse` | `nested` | `conditional` | Warehouse Resolver | `warehouse` | 如填写，必须是 ERPNext Warehouse.name 全称。 | - |

### `erpnext.buying.create_purchase_order_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建采购订单草稿，不提交采购承诺。 |
| Allowed Roles | 采购 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Purchase Order`, `Purchase Order Item`<br>Method: `create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `supplier`、`schedule_date`、`transaction_date`、`company`、`currency`、`buying_price_list`、`items` |

Business Contract：

- 创建前必须确认供应商、公司、物料、数量、价格、交期和仓库/项目归属。
- supplier 必须解析为真实 Supplier.name；若供应商资料显示 prevent_pos，应阻止或升级人工处理。
- 采购订单草稿不提交、不触发正式采购承诺；提交需另走 buying.submit_document。
- 实现约定：Purchase Order 草稿工具应把 buying_price_list 写入 payload；补映射前 Runtime 只把它作为确认摘要和后续修正依据。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `supplier` | `string` | `True` | Supplier Resolver | `supplier` | 必须是 ERPNext Supplier.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `schedule_date` | `string` | `conditional` | Date Resolver | `date` | 必须是 ISO 日期。 | - |
| `transaction_date` | `string` | `conditional` | Date Resolver | `date` | 必须是 ISO 日期。 | - |
| `company` | `string` | `conditional` | Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `currency` | `string` | `no` | - | - | - | - |
| `buying_price_list` | `string` | `no` | - | - | - | - |
| `items` | `array` | `True` | Item Resolver + Slot Extractor | `item` | array_items_schema=true、数组至少 1 行。、每行 qty 必须大于 0，rate 或 price_list_rate 不得为负。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `items[].item_code` | `nested` | `conditional` | Item Resolver | `item` | 必须是已存在、未禁用的 ERPNext Item.item_code。 | - |
| `items[].schedule_date` | `nested` | `conditional` | Date Resolver | `date` | 行级日期缺省时可继承顶层 schedule_date。 | - |
| `items[].warehouse` | `nested` | `conditional` | Warehouse Resolver | `warehouse` | 如填写，必须是 ERPNext Warehouse.name 全称。 | - |

### `erpnext.buying.create_purchase_order_from_material_request_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：从已提交采购类材料申请创建采购订单草稿，保留源单行引用。 |
| Allowed Roles | 采购 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Material Request`, `Material Request Item`, `Purchase Order`, `Purchase Order Item`<br>Method: `get_document`, `create_document`<br>先读取 Material Request 并校验 docstatus/type/剩余可订购数量，再创建 Purchase Order 草稿。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `material_request`、`supplier`、`transaction_date`、`schedule_date`、`company`、`currency`、`selected_items` |

Business Contract：

- material_request 必须是已提交且类型为 Purchase 的 Material Request。
- selected_items 为空时默认尝试全部剩余可订购行；指定行时必须避免 item_code 歧义，必要时使用 material_request_item。
- 所选 qty 必须大于 0 且不能超过源材料申请行剩余可订购数量。
- 生成的采购订单仍是草稿，提交需另走 buying.submit_document。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `material_request` | `string` | `True` | Material Request Resolver | `material_request` | 必须是 ERPNext Material Request.name 全称。、必须是 docstatus=1 且 material_request_type=Purchase 的源单。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `supplier` | `string` | `True` | Supplier Resolver | `supplier` | 必须是 ERPNext Supplier.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `transaction_date` | `string` | `conditional` | Date Resolver | `date` | 必须是 ISO 日期。 | - |
| `schedule_date` | `string` | `conditional` | Date Resolver / 源单默认 | `date` | 缺省时可继承源 Material Request 的 schedule_date。 | - |
| `company` | `string` | `conditional` | Runtime Context / 源单 | `company` | 必须是 ERPNext Company.name 全称；缺省时可继承源单 company。 | `inject_context`、`resolve_entity` |
| `currency` | `string` | `no` | - | - | - | - |
| `selected_items` | `array` | `no` | 源 Material Request 行选择 | `item` | array_items_schema=true、为空表示尝试全部剩余可订购行。、指定 item_code 且匹配多行时，必须改用 material_request_item。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `selected_items[].item_code` | `nested` | `conditional` | Item Resolver / 源单行 | `item` | 如填写，必须匹配源 Material Request 行中的 Item.item_code。 | - |
| `selected_items[].warehouse` | `nested` | `conditional` | Warehouse Resolver / 源单行 | `warehouse` | 如覆盖源单仓库，必须是 ERPNext Warehouse.name 全称。 | - |

### `erpnext.buying.create_purchase_receipt_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：创建采购收货草稿，不提交库存移动。 |
| Allowed Roles | 仓管、采购 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Purchase Receipt`, `Purchase Receipt Item`<br>Method: `create_document` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `supplier`、`posting_date`、`company`、`items` |

Business Contract：

- 创建前必须确认供应商、收货日期、物料、数量和入库仓库。
- 采购收货草稿不提交、不改变库存；提交需另走 buying.submit_document。
- 每行 qty 必须为实际拟收货数量，不能使用模糊数量。
- 默认口径：优先从 Purchase Order 创建采购收货；无源直接收货只允许采购主管/仓库主管在 user_confirm 后创建，并按 Purchase Receipt 元数据补齐必填字段。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `supplier` | `string` | `True` | Supplier Resolver | `supplier` | 必须是 ERPNext Supplier.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `posting_date` | `string` | `conditional` | Date Resolver | `date` | 必须是 ISO 日期。 | `ask_clarification`、`inject_context` |
| `company` | `string` | `conditional` | Runtime Context | `company` | 必须是 ERPNext Company.name 全称。 | `inject_context`、`resolve_entity` |
| `items` | `array` | `True` | Item Resolver + 收货编排 | `item` | array_items_schema=true、数组至少 1 行。、每行 qty 必须大于 0。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `items[].item_code` | `nested` | `conditional` | Item Resolver | `item` | 必须是已存在、未禁用的 ERPNext Item.item_code。 | - |
| `items[].purchase_order` | `nested` | `conditional` | Purchase Order Resolver / 源单行 | `purchase_order` | 如从 PO 收货，必须引用真实 Purchase Order.name。 | - |
| `items[].warehouse` | `nested` | `conditional` | Warehouse Resolver | `warehouse` | 必须是 ERPNext Warehouse.name 全称。 | - |

### `erpnext.buying.create_purchase_receipt_from_purchase_order_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：从已提交采购订单创建采购收货草稿，保留源订单行引用。 |
| Allowed Roles | 仓管、采购 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Purchase Order`, `Purchase Order Item`, `Purchase Receipt`, `Purchase Receipt Item`<br>Method: `get_document`, `create_document`<br>先读取 Purchase Order 并校验 docstatus/status/剩余可收货数量，再创建 Purchase Receipt 草稿。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`inject_context`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `purchase_order`、`posting_date`、`company`、`selected_items` |

Business Contract：

- purchase_order 必须是已提交且未关闭/未取消的采购订单。
- selected_items 为空时默认尝试全部剩余可收货行；指定行时必须避免 item_code 歧义，必要时使用 purchase_order_item。
- 所选 qty 必须大于 0 且不能超过源采购订单行剩余可收货数量。
- 生成的采购收货仍是草稿，提交需另走 buying.submit_document。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `purchase_order` | `string` | `True` | Purchase Order Resolver | `purchase_order` | 必须是 ERPNext Purchase Order.name 全称。、必须是 docstatus=1 且状态未关闭/未取消的源单。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `posting_date` | `string` | `conditional` | Date Resolver | `date` | 必须是 ISO 日期。 | - |
| `company` | `string` | `conditional` | Runtime Context / 源订单 | `company` | 必须是 ERPNext Company.name 全称；缺省时可继承源订单 company。 | `inject_context`、`resolve_entity` |
| `selected_items` | `array` | `no` | 源 Purchase Order 行选择 | `item` | array_items_schema=true、为空表示尝试全部剩余可收货行。、指定 item_code 且匹配多行时，必须改用 purchase_order_item。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `selected_items[].item_code` | `nested` | `conditional` | Item Resolver / 源订单行 | `item` | 如填写，必须匹配源 Purchase Order 行中的 Item.item_code。 | - |
| `selected_items[].warehouse` | `nested` | `conditional` | Warehouse Resolver / 源订单行 | `warehouse` | 如覆盖源订单仓库，必须是 ERPNext Warehouse.name 全称。 | - |

### `erpnext.buying.record_purchase_receipt_discrepancy`

| 项目 | 内容 |
|---|---|
| 用途 | L2：在采购收货单上记录到货差异评论，并可选创建跟进 ToDo；不提交、不退货、不改库存。 |
| Allowed Roles | 仓管、采购、项目经理 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Purchase Receipt`, `Comment`, `ToDo`<br>Method: `get_document`, `add_comment`, `create_todo`<br>会写入审计可追溯评论；prepare_return 只生成退货预览上下文，不创建退货单。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `purchase_receipt`、`description`、`discrepancy_type`、`severity`、`reported_by`、`assigned_to`、`priority`、`due_date`、`create_todo`、`prepare_return`、`full_return`、`items` |

Business Contract：

- 必须有明确 description，说明差异事实、预期与实际情况。
- 本工具只写评论和可选 ToDo，不提交收货、不创建退货草稿、不改变库存。
- 涉及具体物料行时必须引用 purchase_receipt_item 或已解析 item_code，并记录数量、原因和仓库。
- prepare_return/full_return 只能用于返回可退货预览；创建退货草稿必须另走 create_purchase_receipt_return_draft。
- 差异记录必须进入审计字段，便于后续供应商追责或质量处理。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `purchase_receipt` | `string` | `True` | Purchase Receipt Resolver | `purchase_receipt` | 必须是 ERPNext Purchase Receipt.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `description` | `string` | `True` | 用户确认 | - | 必须记录清晰差异说明，不能只写“有问题”。 | `ask_clarification` |
| `discrepancy_type` | `string` | `no` | - | - | - | - |
| `severity` | `string` | `no` | - | - | - | - |
| `reported_by` | `string` | `no` | - | - | - | - |
| `assigned_to` | `string` | `no` | - | - | - | - |
| `priority` | `string` | `no` | - | - | - | - |
| `due_date` | `string` | `conditional` | Date Resolver | `date` | 如创建 ToDo，必须是 ISO 日期或为空由后端默认。 | - |
| `create_todo` | `boolean` | `no` | - | - | - | - |
| `prepare_return` | `boolean` | `no` | - | - | - | - |
| `full_return` | `boolean` | `no` | - | - | - | - |
| `comment_email` | `string` | `no` | - | - | - | - |
| `comment_by` | `string` | `no` | - | - | - | - |
| `items` | `array` | `no` | Purchase Receipt 行上下文 | `item` | array_items_schema=true、可为空；非空时每行 qty 必须大于 0。、每行应包含 expected/actual/reason 中的有效差异信息。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `items[].item_code` | `nested` | `conditional` | Item Resolver / 源收货行 | `item` | 如填写，必须匹配采购收货单中的物料。 | - |
| `items[].warehouse` | `nested` | `conditional` | Warehouse Resolver / 源收货行 | `warehouse` | 如填写，必须是 ERPNext Warehouse.name 全称。 | - |

### `erpnext.buying.get_purchase_receipt_return_context`

| 项目 | 内容 |
|---|---|
| 用途 | L1：预览采购收货单可退货行，供创建供应商退货草稿前校验。 |
| Allowed Roles | 仓管、采购、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Purchase Receipt`, `Purchase Receipt Item`<br>Method: `get_document` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `purchase_receipt`、`full_return`、`items` |

Business Contract：

- 只读退货上下文，不创建退货、不改库存。
- purchase_receipt 必须是已提交的原始采购收货单，不能是退货单。
- items 为空或 full_return=true 时预览全部可退货行；指定行时 qty 不能超过可退数量。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `purchase_receipt` | `string` | `True` | Purchase Receipt Resolver | `purchase_receipt` | 必须是 ERPNext Purchase Receipt.name 全称。、必须是 docstatus=1 且不是 is_return 的原始收货单。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `full_return` | `boolean` | `no` | - | - | - | - |
| `items` | `array` | `no` | Purchase Receipt 行选择 | `item` | array_items_schema=true、为空表示预览全部可退货行。、指定 item_code 且匹配多行时，必须改用 purchase_receipt_item 或 warehouse 缩小范围。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `items[].item_code` | `nested` | `conditional` | Item Resolver / 源收货行 | `item` | 如填写，必须匹配源 Purchase Receipt 行中的 Item.item_code。 | - |
| `items[].warehouse` | `nested` | `conditional` | Warehouse Resolver / 源收货行 | `warehouse` | 如用于缩小匹配范围，必须是 ERPNext Warehouse.name 全称。 | - |

### `erpnext.buying.create_purchase_receipt_return_draft`

| 项目 | 内容 |
|---|---|
| 用途 | L3：从已提交采购收货单创建采购退货草稿，不提交。 |
| Allowed Roles | 仓管、采购 |
| Expose | `agent_visible` |
| Confirm | `user_confirm` |
| Backend Mapping | DocType: `Purchase Receipt`, `Purchase Receipt Item`<br>Method: `get_document`, `create_document`<br>复用退货上下文校验，创建 is_return=1 且 return_against 指向原采购收货单的草稿。 |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `purchase_receipt`、`posting_date`、`full_return`、`reason`、`items` |

Business Contract：

- purchase_receipt 必须是已提交的原始采购收货单，不能是退货单。
- 创建前必须确认退货原因、退货物料行和退货数量。
- 用户输入 qty 使用正数表达拟退数量；后端创建退货行时转换为负数。
- 生成的退货单仍是 Purchase Receipt 草稿，提交需另走 buying.submit_document。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `purchase_receipt` | `string` | `True` | Purchase Receipt Resolver | `purchase_receipt` | 必须是 ERPNext Purchase Receipt.name 全称。、必须是 docstatus=1 且不是 is_return 的原始收货单。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `posting_date` | `string` | `conditional` | Date Resolver | `date` | 必须是 ISO 日期。 | - |
| `full_return` | `boolean` | `no` | - | - | - | - |
| `reason` | `string` | `conditional` | 用户确认 | - | 建议记录退货原因，便于审计。 | `ask_clarification` |
| `items` | `array` | `no` | Purchase Receipt 行选择 | `item` | array_items_schema=true、为空且 full_return=true 时表示全量退货。、指定行 qty 必须大于 0 且不能超过可退数量。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `items[].item_code` | `nested` | `conditional` | Item Resolver / 源收货行 | `item` | 如填写，必须匹配源 Purchase Receipt 行中的 Item.item_code。 | - |
| `items[].warehouse` | `nested` | `conditional` | Warehouse Resolver / 源收货行 | `warehouse` | 如用于缩小匹配范围，必须是 ERPNext Warehouse.name 全称。 | - |

### `erpnext.buying.generate_purchase_suggestions`

| 项目 | 内容 |
|---|---|
| 用途 | L0：基于后端采购建议逻辑生成低库存或待采购建议。 |
| Allowed Roles | 采购、仓管、项目经理、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Item`, `Bin`, `Material Request`<br>Method: `agent_bridge.api.generate_purchase_suggestions`<br>调用桥接业务逻辑生成建议结果，本工具不创建采购单据。 |
| Repair | `erpnext_validation_error`、`permission_denied` |
| 审计重点 | `limit` |

Business Contract：

- 只生成建议，不创建材料申请、询价单或采购订单。
- 建议结果必须由用户确认后，才能进入 create_material_request_draft 或其它创建类工具。
- 实现约定：采购建议算法、库存阈值和排除规则由 agent_bridge.api.generate_purchase_suggestions 后端与配置文件定义，ToolCall 只承诺返回结构和确认边界。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=200、不得超过 schema 上限，避免一次返回过多建议。 | - |

### `erpnext.buying.search_item_suppliers`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询物料供应商关系，用于采购寻源和供应商校验。 |
| Allowed Roles | 采购、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Item Supplier`, `Item`, `Supplier`<br>Method: `search_documents` |
| Repair | `resolve_entity`、`present_candidates`、`ask_clarification`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `item_code`、`supplier`、`limit` |

Business Contract：

- 只读 Item Supplier 关系，不改供应商和物料。
- item_code 和 supplier 可任选其一或同时提供；提供时必须先解析为真实主键。
- 查询结果只能作为采购候选依据，不能自动生成订单。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `conditional` | Item Resolver | `item` | 必须是 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `supplier` | `string` | `conditional` | Supplier Resolver | `supplier` | 必须是 ERPNext Supplier.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100、不得超过 schema 上限。 | - |

### `erpnext.buying.search_item_prices`

| 项目 | 内容 |
|---|---|
| 用途 | L0：查询采购 Item Price，用于价格参考和报价/采购订单草稿前校验。 |
| Allowed Roles | 采购、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Item Price`, `Item`, `Supplier`<br>Method: `search_documents` |
| Repair | `resolve_entity`、`present_candidates`、`ask_clarification`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `item_code`、`price_list`、`supplier`、`currency`、`limit` |

Business Contract：

- 只读采购价格，不创建或修改 Item Price。
- item_code 必须解析为真实 Item.item_code；supplier 如提供必须解析为真实 Supplier.name。
- 价格结果只能作为建议或预填依据，创建报价/订单草稿仍需用户确认。
- 实现约定：Item Price 检索必须固定 buying=1，并在 handler 中落实 supplier/currency 过滤；若站点字段缺失则返回带 debug 的降级结果。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `item_code` | `string` | `conditional` | Item Resolver | `item` | 必须是 ERPNext Item.item_code。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `price_list` | `string` | `no` | Buying Price List Resolver / 用户选择 | - | 默认口径：价格表必须通过 Price List resolver 精确命中且 buying=1；无匹配时不填价格表并提示用户选择。 | - |
| `supplier` | `string` | `conditional` | Supplier Resolver | `supplier` | 如提供，必须是 ERPNext Supplier.name 全称。 | `resolve_entity`、`present_candidates`、`ask_clarification` |
| `currency` | `string` | `no` | Currency Resolver / 用户选择 | - | 默认口径：currency 优先过滤 Item Price.currency；若站点价格表币种与价格行分离，则由 Price List resolver 补充校验。 | - |
| `limit` | `integer` | `no` | Runtime 默认值 | - | minimum=1、maximum=100、不得超过 schema 上限。 | - |

### `erpnext.buying.get_buying_settings`

| 项目 | 内容 |
|---|---|
| 用途 | L0：读取 Buying Settings 单例配置。 |
| Allowed Roles | 采购、管理层、developer |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Buying Settings`<br>Method: `get_document` |
| Repair | `erpnext_validation_error`、`permission_denied` |
| 审计重点 | - |

Business Contract：

- 只读采购设置，不修改系统配置。
- 设置项只能作为解释和后续工具参数校验依据。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| - | - | - | - | - | - | - |

### `erpnext.buying.run_purchase_analysis`

| 项目 | 内容 |
|---|---|
| 用途 | L1：运行采购分析类标准报表，返回只读分析结果。 |
| Allowed Roles | 采购、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Purchase Order`, `Purchase Receipt`, `Supplier`, `Item`<br>Method: `run_report`<br>默认报表为 Purchase Analytics，filters 由报表工具规范化。 |
| Repair | `resolve_entity`、`ask_clarification`、`inject_context`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `report_name`、`filters` |

Business Contract：

- 只读报表，不创建、不修改采购单据。
- filters 必须由 Runtime 或报表编排层构造，禁止模型手写不受控 Frappe filter DSL。
- 涉及公司、供应商、物料、日期的 filters 必须先通过对应 resolver。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `report_name` | `string` | `no` | Runtime 默认 / 用户选择 | - | 默认 Purchase Analytics；其它报表名需确认 ERPNext 实例存在。 | - |
| `filters` | `object` | `no` | Runtime Report Filter Builder | - | 必须是报表工具可接受的对象。 | `validate_before_execute`、`inject_context` |
| `filters.company` | `nested` | `conditional` | Company Resolver / Runtime Context | `company` | 如提供，必须是 ERPNext Company.name 全称。 | - |
| `filters.from_date` | `nested` | `conditional` | Date Resolver | `date` | 如提供，必须是 ISO 日期。 | - |
| `filters.item_code` | `nested` | `conditional` | Item Resolver | `item` | 如提供，必须是 ERPNext Item.item_code。 | - |
| `filters.supplier` | `nested` | `conditional` | Supplier Resolver | `supplier` | 如提供，必须是 ERPNext Supplier.name 全称。 | - |
| `filters.to_date` | `nested` | `conditional` | Date Resolver | `date` | 如提供，必须是 ISO 日期。 | - |

### `erpnext.buying.compare_supplier_quotations`

| 项目 | 内容 |
|---|---|
| 用途 | L1：比较供应商报价单总额和明细价格，不授标、不创建采购订单。 |
| Allowed Roles | 采购、管理层 |
| Expose | `agent_visible` |
| Confirm | `none` |
| Backend Mapping | DocType: `Supplier Quotation`, `Supplier Quotation Item`<br>Method: `get_document` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `supplier_quotations`、`include_drafts` |

Business Contract：

- 至少需要两张 Supplier Quotation 才能比较。
- 比较结果只作为采购决策参考，不自动选择供应商、不创建 PO。
- include_drafts=true 时必须在结果中提示包含草稿，避免把未提交报价当作正式报价。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `supplier_quotations` | `array` | `True` | Supplier Quotation Resolver / 用户确认 | `supplier_quotation` | array_items_schema=true、数组至少 2 个 Supplier Quotation.name。、每个名称必须能读取到真实 Supplier Quotation。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `include_drafts` | `boolean` | `no` | 用户选择 / Runtime 默认 | - | 默认为 false；包含草稿时必须显式标注。 | - |

### `erpnext.buying.submit_document`

| 项目 | 内容 |
|---|---|
| 用途 | L4：提交采购相关单据，触发正式业务状态变更。 |
| Allowed Roles | 采购、仓管、管理层 |
| Expose | `agent_visible` |
| Confirm | `submit_confirm` |
| Backend Mapping | DocType: `Material Request`, `Request for Quotation`, `Supplier Quotation`, `Purchase Order`, `Purchase Receipt`<br>Method: `submit_document` |
| Repair | `resolve_entity`、`ask_clarification`、`present_candidates`、`validate_before_execute`、`erpnext_validation_error`、`permission_denied` |
| 审计重点 | `doctype`、`name`、`confirmation` |

Business Contract：

- 提交前必须已有明确 submit_confirm，confirmation 必须包含 confirmed_by、confirmed_at、confirmation_text 和 reason。
- 只允许提交 schema 枚举中的采购 DocType，不允许提交任意 DocType。
- 提交 Purchase Order 表示正式采购承诺；提交 Purchase Receipt 可能影响库存和财务后续流程。
- 提交前必须向用户复述 doctype、name、关键金额/数量/供应商/公司和下游影响。
- 默认口径：提交前读取目标 DocType 元数据和 Workflow 状态；审批流存在时优先走 apply_workflow，普通提交由 ERPNext 权限和必填字段校验兜底。

核心入参：

| 参数 | 类型 | 必填 | 来源 | Resolver | 约束 | Repair |
|---|---|---|---|---|---|---|
| `doctype` | `enum` | `True` | Tool enum | - | 只能是 Material Request、Request for Quotation、Supplier Quotation、Purchase Order、Purchase Receipt。 | `validate_before_execute`、`ask_clarification` |
| `name` | `string` | `True` | Doctype-aware Document Resolver | `buying_document` | 必须是所选 doctype 下真实存在的文档 name。、当 doctype=Material Request 时必须使用 Material Request Resolver；doctype=Purchase Order 时必须使用 Purchase Order Resolver；doctype=Purchase Receipt 时必须使用 Purchase Receipt Resolver。 | `resolve_entity`、`present_candidates`、`ask_clarification`、`validate_before_execute` |
| `confirmation` | `object` | `True` | Submit Confirmation Gate | - | 必须证明用户已明确同意提交，而不是只同意创建草稿。、confirmation.confirmed 必须为 true，且 reason 不能为空。 | `ask_clarification`、`validate_before_execute` |


## 全量参数索引

说明：这里先列代码 schema 中的基础参数。更严格的业务约束以人工补充详情和 `config/tool_contracts/*.yaml` 为准。

| ToolCall | 参数索引 |
|---|---|
| `erpnext.get_logged_user` | - |
| `erpnext.search_documents` | `doctype:string/可选`, `filters:object|array/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.search_items` | `query:string/可选`, `specs:object/可选`, `item_group:string/可选`, `enabled_only:boolean/可选`, `limit:integer/可选` |
| `erpnext.count_documents` | `doctype:string/可选`, `filters:object|array/可选` |
| `erpnext.get_document` | `doctype:string/可选`, `name:string/可选` |
| `erpnext.create_document` | `doctype:string/可选`, `data:object/可选` |
| `erpnext.update_document` | `doctype:string/可选`, `name:string/可选`, `data:object/可选` |
| `erpnext.delete_document` | `doctype:string/可选`, `name:string/可选` |
| `erpnext.document_exists` | `doctype:string/可选`, `name:string/可选` |
| `erpnext.resolve_link` | `doctype:string/可选`, `query:string/可选`, `search_field:string/可选`, `limit:integer/可选` |
| `erpnext.validate_fields` | `doctype:string/可选`, `fields:array/可选` |
| `erpnext.get_doctype_schema` | `doctype:string/可选` |
| `erpnext.submit_document` | `doctype:string/可选`, `name:string/可选`, `confirmation:object/条件必填` |
| `erpnext.cancel_document` | `doctype:string/可选`, `name:string/可选`, `confirmation:object/条件必填` |
| `erpnext.amend_document` | `doctype:string/必填`, `name:string/必填` |
| `erpnext.get_workflow_actions` | `doctype:string/必填`, `name:string/必填` |
| `erpnext.apply_workflow` | `doctype:string/可选`, `name:string/可选`, `action:string/可选` |
| `erpnext.run_report` | `report_name:string/必填`, `filters:object/可选`, `ignore_prepared_report:boolean/可选` |
| `erpnext.users.list_users` | `query:string/可选`, `enabled:boolean/可选`, `user_type:string/可选`, `role_profile_name:string/可选`, `limit:integer/可选`, `offset:integer/可选` |
| `erpnext.users.get_user_access_summary` | `user:string/可选`, `include_permissions:boolean/可选` |
| `erpnext.users.list_roles` | `query:string/可选`, `disabled:boolean/可选`, `desk_access:boolean/可选`, `limit:integer/可选`, `offset:integer/可选` |
| `erpnext.users.list_role_profiles` | `query:string/可选`, `limit:integer/可选`, `offset:integer/可选` |
| `erpnext.users.preview_role_profile_roles` | `role_profile:string/可选` |
| `erpnext.users.list_user_permissions` | `user:string/可选`, `allow:string/可选`, `for_value:string/可选`, `applicable_for:string/可选`, `limit:integer/可选`, `offset:integer/可选` |
| `erpnext.users.list_shared_documents` | `user:string/可选`, `share_doctype:string/可选`, `share_name:string/可选`, `limit:integer/可选`, `offset:integer/可选` |
| `erpnext.users.list_access_logs` | `user:string/可选`, `limit:integer/可选`, `offset:integer/可选` |
| `erpnext.users.list_activity_logs` | `user:string/可选`, `subject:string/可选`, `limit:integer/可选`, `offset:integer/可选` |
| `erpnext.users.get_permission_metadata` | `doctype:string/可选` |
| `erpnext.users.preview_effective_permissions` | `user:string/可选`, `doctype:string/可选`, `include_user_permissions:boolean/可选` |
| `erpnext.users.check_server_permission` | `user:string/可选`, `doctype:string/可选`, `docname:string/可选`, `action:enum/可选`, `debug:boolean/可选` |
| `erpnext.users.preview_permission_policy_change` | `doctype:string/可选`, `changes:array/可选` |
| `erpnext.users.create_user_draft` | `email:string/可选`, `first_name:string/可选`, `last_name:string/可选`, `user_type:string/可选`, `role_profile_name:string/可选`, `roles:array/可选`, `enabled:boolean/可选`, `send_welcome_email:boolean/可选`, `confirmation:object/可选` |
| `erpnext.users.set_user_enabled` | `user:string/可选`, `enabled:boolean/可选`, `confirmation:object/可选` |
| `erpnext.users.assign_roles` | `user:string/可选`, `mode:enum/可选`, `roles:array/可选`, `confirmation:object/可选` |
| `erpnext.users.create_user_permission` | `user:string/可选`, `allow:string/可选`, `for_value:string/可选`, `applicable_for:string/可选`, `is_default:boolean/可选`, `hide_descendants:boolean/可选`, `confirmation:object/可选` |
| `erpnext.users.delete_user_permission` | `name:string/可选`, `confirmation:object/可选` |
| `erpnext.accounting.search_accounts` | `company:string/可选`, `account_type:string/可选`, `filters:object|array/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.accounting.search_cost_centers` | `company:string/可选`, `filters:object|array/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.accounting.search_budgets` | `company:string/可选`, `fiscal_year:string/可选`, `filters:object|array/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.accounting.search_fiscal_years` | `year:string/可选`, `disabled:boolean/可选`, `filters:object|array/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.accounting.search_accounting_periods` | `company:string/可选`, `from_date:string/可选`, `to_date:string/可选`, `filters:object|array/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.accounting.search_payment_terms` | `doctype:enum/可选`, `query:string/可选`, `filters:object|array/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.accounting.search_tax_templates` | `template_type:enum/可选`, `query:string/可选`, `company:string/可选`, `tax_category:string/可选`, `disabled:boolean/可选`, `filters:object|array/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.accounting.get_report_filters` | `report_name:enum/可选` |
| `erpnext.accounting.general_ledger` | `company:string/可选`, `from_date:string/可选`, `to_date:string/可选`, `account:string/可选`, `party_type:string/可选`, `party:string/可选`, `filters:object/可选` |
| `erpnext.accounting.accounts_receivable` | `company:string/可选`, `from_date:string/可选`, `to_date:string/可选`, `party:string/可选`, `filters:object/可选` |
| `erpnext.accounting.accounts_payable` | `company:string/可选`, `from_date:string/可选`, `to_date:string/可选`, `party:string/可选`, `filters:object/可选` |
| `erpnext.accounting.financial_report` | `report_name:enum/可选`, `company:string/可选`, `from_date:string/可选`, `to_date:string/可选`, `fiscal_year:string/可选`, `filters:object/可选` |
| `erpnext.accounting.create_journal_entry_draft` | `data:object/可选` |
| `erpnext.accounting.create_payment_entry_draft` | `data:object/可选` |
| `erpnext.accounting.create_sales_invoice_draft` | `data:object/可选` |
| `erpnext.accounting.create_purchase_invoice_draft` | `data:object/可选` |
| `erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft` | `purchase_receipt:string/可选`, `posting_date:string/可选`, `bill_no:string/可选`, `bill_date:string/可选`, `company:string/可选`, `selected_items:array/可选` |
| `erpnext.accounting.create_period_closing_voucher_draft` | `data:object/可选` |
| `erpnext.accounting.prepare_payment_allocation` | `party_type:enum/可选`, `party:string/可选`, `payment_type:enum/可选`, `invoice_doctype:enum/可选`, `invoice_names:array/可选`, `company:string/可选`, `paid_amount:number/可选`, `allocations:object/可选`, `limit:integer/可选`, `order_by:string/可选` |
| `erpnext.accounting.prepare_invoice_taxes` | `invoice_type:enum/可选`, `taxes_and_charges:string/可选`, `items:array/可选`, `taxes:array/可选`, `net_total:number/可选` |
| `erpnext.accounting.prepare_bank_reconciliation` | `company:string/可选`, `bank_account:string/可选`, `status:string/可选`, `from_date:string/可选`, `to_date:string/可选`, `limit:integer/可选`, `order_by:string/可选` |
| `erpnext.accounting.apply_bank_reconciliation` | `bank_transaction:string/可选`, `matches:array/可选`, `replace_existing:boolean/可选`, `remarks:string/可选`, `confirmation:object/可选` |
| `erpnext.accounting.create_budget_draft` | `data:object/可选` |
| `erpnext.accounting.update_budget_draft` | `name:string/可选`, `data:object/可选` |
| `erpnext.accounting.submit_financial_document` | `doctype:enum/可选`, `name:string/可选`, `confirmation:object/可选` |
| `erpnext.assets.search_assets` | `query:string/可选`, `company:string/可选`, `asset_category:string/可选`, `location:string/可选`, `status:string/可选`, `item_code:string/可选`, `custodian:string/可选`, `filters:object|array/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.assets.search_asset_categories` | `query:string/可选`, `filters:object|array/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.assets.search_asset_locations` | `query:string/可选`, `filters:object|array/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.assets.get_financial_snapshot` | `asset:string/可选`, `finance_book:string/可选`, `include_depreciation_schedules:boolean/可选`, `include_schedule_rows:boolean/可选`, `schedule_limit:integer/可选` |
| `erpnext.assets.get_depreciation_schedule` | `asset:string/可选`, `finance_book:string/可选`, `status:string/可选`, `include_rows:boolean/可选`, `only_due_before:string/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.assets.create_asset_draft` | `data:object/可选` |
| `erpnext.assets.create_movement_draft` | `data:object/可选` |
| `erpnext.assets.create_maintenance_draft` | `data:object/可选` |
| `erpnext.assets.create_maintenance_log_draft` | `data:object/可选` |
| `erpnext.assets.create_repair_draft` | `data:object/可选` |
| `erpnext.assets.create_value_adjustment_draft` | `data:object/可选` |
| `erpnext.assets.prepare_disposal_or_sale` | `asset:string/可选`, `action:enum/可选`, `posting_date:string/可选`, `proceeds_amount:number/可选`, `party_type:string/可选`, `party:string/可选`, `reason:string/可选` |
| `erpnext.assets.submit_document` | `doctype:enum/可选`, `name:string/可选`, `confirmation:object/可选` |
| `erpnext.stock.get_balance` | `item_code:string/条件必填`, `item_query:string/条件必填`, `warehouse:string/条件必填`, `specs:object/可选`, `item_group:string/可选`, `limit:integer/可选` |
| `erpnext.stock.get_item_locations` | `item_code:string/条件必填`, `item_query:string/条件必填`, `selected_item_code:string/条件必填`, `selection_confirmed:boolean/可选`, `specs:object/可选`, `item_group:string/可选`, `include_zero:boolean/可选`, `limit:integer/可选` |
| `erpnext.stock.get_ledger_entries` | `item_code:string/可选`, `warehouse:string/可选`, `voucher_type:string/可选`, `voucher_no:string/可选`, `limit:integer/可选` |
| `erpnext.stock.get_stock_settings` | - |
| `erpnext.stock.resolve_item` | `query:string/可选`, `specs:object/可选`, `item_group:string/可选`, `enabled_only:boolean/可选`, `limit:integer/可选`, `catalog_database_url:string/可选` |
| `erpnext.stock.create_entry_draft` | `stock_entry_type:string/可选`, `purpose:string/可选`, `company:string/条件必填`, `posting_date:string/条件必填`, `posting_time:string/可选`, `remarks:string/可选`, `items:array/可选` |
| `erpnext.stock.create_reconciliation_draft` | `company:string/条件必填`, `posting_date:string/条件必填`, `posting_time:string/可选`, `purpose:string/可选`, `expense_account:string/可选`, `cost_center:string/可选`, `remarks:string/条件必填`, `items:array/可选` |
| `erpnext.stock.search_batches` | `item_code:string/可选`, `item_query:string/可选`, `query:string/可选`, `limit:integer/可选` |
| `erpnext.stock.list_batch_balances` | `item_code:string/条件必填`, `item_query:string/条件必填`, `selected_item_code:string/条件必填`, `selection_confirmed:boolean/可选`, `batch_no:string/可选`, `query:string/可选`, `warehouse:string/可选`, `include_expired:boolean/可选`, `include_zero:boolean/可选`, `as_of_date:string/可选`, `limit:integer/可选`, `batch_limit:integer/可选`, `ledger_limit:integer/可选` |
| `erpnext.stock.search_serial_numbers` | `item_code:string/可选`, `item_query:string/可选`, `warehouse:string/可选`, `status:string/可选`, `query:string/可选`, `limit:integer/可选` |
| `erpnext.stock.create_batch` | `data:object/可选` |
| `erpnext.stock.update_batch` | `name:string/可选`, `data:object/可选`, `confirmation:object/可选` |
| `erpnext.stock.create_serial_no` | `data:object/可选` |
| `erpnext.stock.update_serial_no` | `name:string/可选`, `data:object/可选`, `confirmation:object/可选` |
| `erpnext.stock.list_pick_lists` | `purpose:string/可选`, `status:string/可选`, `customer:string/可选`, `limit:integer/可选` |
| `erpnext.stock.create_pick_list_draft` | `purpose:string/可选`, `customer:string/可选`, `work_order:string/可选`, `material_request:string/可选`, `sales_order:string/可选`, `parent_warehouse:string/可选`, `locations:array/可选` |
| `erpnext.stock.list_reservations` | `item_code:string/可选`, `item_query:string/可选`, `warehouse:string/可选`, `voucher_type:string/可选`, `voucher_no:string/可选`, `status:string/可选`, `limit:integer/可选` |
| `erpnext.stock.create_reservation_draft` | `item_code:string/条件必填`, `item_query:string/条件必填`, `selected_item_code:string/条件必填`, `selection_confirmed:boolean/可选`, `warehouse:string/可选`, `voucher_type:string/可选`, `voucher_no:string/可选`, `voucher_detail_no:string/可选`, `reserved_qty:number/可选`, `company:string/可选`, `stock_uom:string/可选`, `from_voucher_type:string/可选` |
| `erpnext.stock.preview_valuation` | `items:array/可选` |
| `erpnext.stock.allocate_shortages` | `items:array/可选` |
| `erpnext.stock.list_delivery_notes` | `customer:string/可选`, `status:string/可选`, `docstatus:integer/可选`, `limit:integer/可选` |
| `erpnext.stock.list_purchase_receipts` | `supplier:string/可选`, `status:string/可选`, `docstatus:integer/可选`, `limit:integer/可选` |
| `erpnext.stock.get_document_impact` | `doctype:enum/可选`, `name:string/可选`, `limit:integer/可选` |
| `erpnext.stock.list_item_reorders` | `item_code:string/可选`, `item_query:string/可选`, `warehouse:string/可选`, `material_request_type:string/可选`, `limit:integer/可选` |
| `erpnext.stock.list_quality_inspections` | `item_code:string/可选`, `item_query:string/可选`, `reference_type:string/可选`, `reference_name:string/可选`, `inspection_type:string/可选`, `status:string/可选`, `docstatus:integer/可选`, `limit:integer/可选` |
| `erpnext.stock.create_quality_inspection_draft` | `item_code:string/条件必填`, `item_query:string/条件必填`, `selected_item_code:string/条件必填`, `selection_confirmed:boolean/可选`, `inspection_type:string/可选`, `reference_type:string/可选`, `reference_name:string/可选`, `sample_size:number/可选`, `inspected_by:string/可选`, `verified_by:string/可选`, `report_date:string/可选`, `status:string/可选`, `remarks:string/可选`, `readings:array/可选` |
| `erpnext.stock.verify_purchase_receipt_stock_impact` | `purchase_receipt:string/可选`, `item_code:string/可选`, `warehouse:string/可选`, `limit:integer/可选` |
| `erpnext.stock.get_item_lifecycle_summary` | `item_code:string/条件必填`, `item_query:string/条件必填`, `selected_item_code:string/条件必填`, `selection_confirmed:boolean/可选`, `project:string/可选`, `warehouse:string/可选`, `from_date:string/可选`, `to_date:string/可选`, `limit:integer/可选` |
| `erpnext.stock.list_warehouses` | `company:string/可选`, `query:string/可选`, `limit:integer/可选` |
| `erpnext.stock.create_warehouse` | `data:object/可选` |
| `erpnext.stock.update_warehouse` | `name:string/可选`, `data:object/可选` |
| `erpnext.stock.list_item_groups` | `query:string/可选`, `parent_item_group:string/可选`, `is_group:boolean/可选`, `filters:object/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.stock.create_item_group` | `data:object/可选` |
| `erpnext.stock.update_item_group` | `name:string/可选`, `data:object/可选` |
| `erpnext.stock.list_uoms` | `query:string/可选`, `enabled:boolean/可选`, `filters:object/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.stock.create_uom` | `data:object/可选` |
| `erpnext.stock.update_uom` | `name:string/可选`, `data:object/可选` |
| `erpnext.stock.submit_document` | `doctype:enum/可选`, `name:string/可选`, `confirmation:object/可选` |
| `erpnext.projects.get_project_cost_context` | `project:string/可选`, `company:string/可选`, `from_date:string/可选`, `to_date:string/可选`, `include_tasks:boolean/可选`, `include_stock_entries:boolean/可选`, `include_purchase_receipts:boolean/可选`, `limit:integer/可选` |
| `erpnext.projects.get_material_issue_context` | `project:string/可选`, `source_warehouse:string/可选`, `items:array/可选` |
| `erpnext.projects.create_material_issue_draft` | `project:string/可选`, `source_warehouse:string/可选`, `company:string/可选`, `posting_date:string/可选`, `posting_time:string/可选`, `cost_center:string/可选`, `expense_account:string/可选`, `remarks:string/可选`, `require_available_stock:boolean/可选`, `items:array/可选` |
| `erpnext.projects.verify_material_issue_cost_impact` | `stock_entry:string/可选`, `project:string/可选`, `limit:integer/可选` |
| `erpnext.setup_item_master` | - |
| `erpnext.prepare_item_from_intent` | `intent:object/必填` |
| `erpnext.create_item_from_intent` | `intent:object/必填` |
| `erpnext.create_todo` | `description:string/可选`, `allocated_to:string/可选`, `priority:string/可选`, `reference_type:string/可选`, `reference_name:string/可选`, `date:string/可选` |
| `erpnext.add_comment` | `reference_doctype:string/可选`, `reference_name:string/可选`, `content:string/可选`, `comment_email:string/可选`, `comment_by:string/可选` |
| `erpnext.get_comments` | `reference_doctype:string/必填`, `reference_name:string/必填`, `limit:integer/可选` |
| `erpnext.assign_to` | `doctype:string/可选`, `name:string/可选`, `assign_to:array/可选`, `description:string/可选`, `priority:string/可选`, `date:string/可选` |
| `erpnext.clear_assignment` | `doctype:string/必填`, `name:string/必填`, `assign_to:string/必填` |
| `erpnext.attach_file` | `doctype:string/必填`, `name:string/必填`, `file_path:string/必填`, `is_private:boolean/可选`, `fieldname:string/可选` |
| `erpnext.list_attachments` | `doctype:string/必填`, `name:string/必填` |
| `erpnext.delete_attachment` | `file_name:string/可选` |
| `erpnext.call_method` | `method:string/可选`, `args:object/可选`, `http_method:enum/可选`, `confirmation:object/可选` |
| `erpnext.buying.search_suppliers` | `query:string/可选`, `supplier_group:string/可选`, `supplier_type:string/可选`, `disabled:boolean/可选`, `is_frozen:boolean/可选`, `on_hold:boolean/可选`, `fields:array/可选`, `limit:integer/可选` |
| `erpnext.buying.search_supplier_scorecards` | `supplier:string/条件必填`, `status:string/可选`, `fields:array/可选`, `limit:integer/可选`, `offset:integer/可选`, `order_by:string/可选` |
| `erpnext.buying.get_supplier_procurement_profile` | `supplier:string/可选`, `company:string/条件必填`, `item_code:string/条件必填`, `currency:string/可选`, `price_list:string/可选`, `scorecard_limit:integer/可选` |
| `erpnext.buying.create_supplier_group_draft` | `supplier_group_name:string/可选`, `parent_supplier_group:string/条件必填`, `is_group:boolean/可选` |
| `erpnext.buying.create_supplier_draft` | `supplier_name:string/可选`, `supplier_group:string/条件必填`, `supplier_type:string/可选`, `country:string/可选`, `tax_id:string/可选`, `default_currency:string/可选` |
| `erpnext.buying.create_material_request_draft` | `material_request_type:string/可选`, `schedule_date:string/条件必填`, `company:string/条件必填`, `items:array/可选`, `items[].item_code:nested/条件必填`, `items[].schedule_date:nested/条件必填`, `items[].warehouse:nested/条件必填` |
| `erpnext.buying.create_request_for_quotation_draft` | `transaction_date:string/条件必填`, `schedule_date:string/条件必填`, `company:string/条件必填`, `message_for_supplier:string/可选`, `suppliers:array/可选`, `items:array/可选`, `items[].item_code:nested/条件必填`, `items[].schedule_date:nested/条件必填`, `items[].warehouse:nested/条件必填` |
| `erpnext.buying.create_supplier_quotation_draft` | `supplier:string/可选`, `transaction_date:string/条件必填`, `valid_till:string/条件必填`, `company:string/条件必填`, `currency:string/可选`, `buying_price_list:string/可选`, `items:array/可选`, `items[].item_code:nested/条件必填`, `items[].warehouse:nested/条件必填` |
| `erpnext.buying.create_purchase_order_draft` | `supplier:string/可选`, `schedule_date:string/条件必填`, `transaction_date:string/条件必填`, `company:string/条件必填`, `currency:string/可选`, `buying_price_list:string/可选`, `items:array/可选`, `items[].item_code:nested/条件必填`, `items[].schedule_date:nested/条件必填`, `items[].warehouse:nested/条件必填` |
| `erpnext.buying.create_purchase_order_from_material_request_draft` | `material_request:string/可选`, `supplier:string/可选`, `transaction_date:string/条件必填`, `schedule_date:string/条件必填`, `company:string/条件必填`, `currency:string/可选`, `selected_items:array/可选`, `selected_items[].item_code:nested/条件必填`, `selected_items[].warehouse:nested/条件必填` |
| `erpnext.buying.create_purchase_receipt_draft` | `supplier:string/可选`, `posting_date:string/条件必填`, `company:string/条件必填`, `items:array/可选`, `items[].item_code:nested/条件必填`, `items[].purchase_order:nested/条件必填`, `items[].warehouse:nested/条件必填` |
| `erpnext.buying.create_purchase_receipt_from_purchase_order_draft` | `purchase_order:string/可选`, `posting_date:string/条件必填`, `company:string/条件必填`, `selected_items:array/可选`, `selected_items[].item_code:nested/条件必填`, `selected_items[].warehouse:nested/条件必填` |
| `erpnext.buying.record_purchase_receipt_discrepancy` | `purchase_receipt:string/可选`, `description:string/可选`, `discrepancy_type:string/可选`, `severity:string/可选`, `reported_by:string/可选`, `assigned_to:string/可选`, `priority:string/可选`, `due_date:string/条件必填`, `create_todo:boolean/可选`, `prepare_return:boolean/可选`, `full_return:boolean/可选`, `comment_email:string/可选`, `comment_by:string/可选`, `items:array/可选`, `items[].item_code:nested/条件必填`, `items[].warehouse:nested/条件必填` |
| `erpnext.buying.get_purchase_receipt_return_context` | `purchase_receipt:string/可选`, `full_return:boolean/可选`, `items:array/可选`, `items[].item_code:nested/条件必填`, `items[].warehouse:nested/条件必填` |
| `erpnext.buying.create_purchase_receipt_return_draft` | `purchase_receipt:string/可选`, `posting_date:string/条件必填`, `full_return:boolean/可选`, `reason:string/条件必填`, `items:array/可选`, `items[].item_code:nested/条件必填`, `items[].warehouse:nested/条件必填` |
| `erpnext.buying.generate_purchase_suggestions` | `limit:integer/可选` |
| `erpnext.buying.search_item_suppliers` | `item_code:string/条件必填`, `supplier:string/条件必填`, `limit:integer/可选` |
| `erpnext.buying.search_item_prices` | `item_code:string/条件必填`, `price_list:string/可选`, `supplier:string/条件必填`, `currency:string/可选`, `limit:integer/可选` |
| `erpnext.buying.get_buying_settings` | - |
| `erpnext.buying.run_purchase_analysis` | `report_name:string/可选`, `filters:object/可选`, `filters.company:nested/条件必填`, `filters.from_date:nested/条件必填`, `filters.item_code:nested/条件必填`, `filters.supplier:nested/条件必填`, `filters.to_date:nested/条件必填` |
| `erpnext.buying.compare_supplier_quotations` | `supplier_quotations:array/可选`, `include_drafts:boolean/可选` |
| `erpnext.buying.submit_document` | `doctype:enum/可选`, `name:string/可选`, `confirmation:object/可选` |

## 维护方式

更新流程：

1. 修改 `config/tool_contracts/*.yaml` 中对应模块文件。
2. 运行 `python scripts/docs/generate_toolcall_data_dictionary.py`。
3. 运行 `python -m pytest tests/unit/agent_runtime/test_tool_contracts.py -q`。

验收规则：

- 150 个 Tool schema 必须都有 Tool contract。
- `developer_only` 不得出现在员工 profile 的 schema 列表。
- `runtime_internal` 只能由 Runtime origin 调用。
- 高风险工具必须有 Confirm。
- 涉及主数据外键的参数必须逐步补 Resolver 和 Repair。
