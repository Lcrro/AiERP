# ToolCall 五大模块控制矩阵

最后更新：2026-06-09

这个文档回答一个问题：

```text
Users & Permissions、资产、库存、采购、财务
目前有哪些 ERPNext 功能已经可以通过 ToolCall 控制？
```

当前已验证的工具注册状态：

```text
137 个 tool schema
137 个 adapter handler
missing = []
extra = []
```

五个重点模块的工具数量：

| 模块 | Tool 前缀 | Tool 数量 |
| --- | --- | ---: |
| Users & Permissions / 用户与权限 | `erpnext.users.*` | 18 |
| Assets / 资产 | `erpnext.assets.*` | 13 |
| Stock / 库存 | `erpnext.stock.*` | 35 |
| Buying / 采购 | `erpnext.buying.*` | 17 |
| Accounting / 财务 | `erpnext.accounting.*` | 24 |

当前验证结果：

```text
五个重点模块单元测试：60 passed
无本地凭据全量测试：97 passed, 3 skipped
加载本地 sandbox .env 全量测试：100 passed
```

## 控制级别

| 级别 | 含义 |
| --- | --- |
| 读取 | 只读取 ERPNext 数据，不改变业务状态。 |
| 预览 | 计算、模拟、检查或生成建议，不写入 ERPNext。 |
| 草稿写入 | 创建或更新草稿/主数据，通常保持 `docstatus = 0`。 |
| 确认执行 | 只有提供确认信息后才执行较高风险动作。 |
| 未覆盖 | 还没有专用模块 ToolCall；简单读取可能仍可用通用工具完成。 |

ToolCall 当前使用的风险等级：

| 风险等级 | 含义 |
| --- | --- |
| `L0` | 只读。 |
| `L1` | 预览、校验、准备、推荐。 |
| `L3` | 草稿单据或主数据写入。 |
| `L4` | 已提交的业务操作，例如库存或采购提交。 |
| `L5_ADMIN` | 用户、角色、权限、系统访问变更。 |
| `L5_FINANCIAL` | 会计分录、付款、发票、折旧或其他财务过账影响。 |

## Users & Permissions / 用户与权限

当前覆盖范围：

```text
User, Role, Role Profile, User Permission, DocShare,
Access Log, Activity Log, DocType permission metadata
```

| ERPNext 功能 | ToolCall | 控制级别 | 风险 | 当前能力 |
| --- | --- | --- | --- | --- |
| 用户列表 | `erpnext.users.list_users` | 读取 | `L0` | 列出用户身份、启用状态、用户类型、角色配置和登录时间。 |
| 用户访问摘要 | `erpnext.users.get_user_access_summary` | 读取 | `L0` | 读取单个用户的角色、角色配置、启用状态和直接 User Permission。 |
| 角色列表 | `erpnext.users.list_roles` | 读取 | `L0` | 列出 Role 记录。 |
| 角色配置列表 | `erpnext.users.list_role_profiles` | 读取 | `L0` | 列出 Role Profile 记录。 |
| 角色配置展开预览 | `erpnext.users.preview_role_profile_roles` | 预览 | `L0` | 展开某个 Role Profile 会赋予哪些角色。 |
| 用户权限列表 | `erpnext.users.list_user_permissions` | 读取 | `L0` | 按用户、允许的 DocType、值或适用 DocType 列出 User Permission。 |
| 共享文档列表 | `erpnext.users.list_shared_documents` | 读取 | `L0` | 列出某个用户或某个文档的 DocShare 记录。 |
| 访问日志 | `erpnext.users.list_access_logs` | 读取 | `L0` | 读取 Access Log，用于审计。 |
| 活动日志 | `erpnext.users.list_activity_logs` | 读取 | `L0` | 读取 Activity Log，用于审计。 |
| 权限元数据 | `erpnext.users.get_permission_metadata` | 读取 | `L0` | 读取 DocType 权限元数据，包括类似 DocPerm 的权限行。 |
| 有效权限预览 | `erpnext.users.preview_effective_permissions` | 预览 | `L0` | 基于元数据预览某用户对某 DocType 的权限；不是完整运行时权限判断。 |
| 服务端运行时权限检查 | `erpnext.users.check_server_permission` | 读取 / 检查 | `L0` | 通过 `agent_bridge.api.check_user_permission` 调用 Frappe 权限引擎。 |
| 权限策略差异预览 | `erpnext.users.preview_permission_policy_change` | 预览 | `L5_ADMIN` | 模拟 DocPerm 风格的 add/update/remove，返回 before/after/diff，不写入 ERPNext。 |
| 创建用户 | `erpnext.users.create_user_draft` | 确认执行 | `L5_ADMIN` | 只有明确确认后才创建 User，默认倾向于禁用/不发欢迎邮件。 |
| 启用/禁用用户 | `erpnext.users.set_user_enabled` | 确认执行 | `L5_ADMIN` | 明确确认后启用或禁用用户。 |
| 分配用户角色 | `erpnext.users.assign_roles` | 确认执行 | `L5_ADMIN` | 明确确认后添加、移除或替换 `Has Role` 行。 |
| 创建用户权限 | `erpnext.users.create_user_permission` | 确认执行 | `L5_ADMIN` | 明确确认后创建 User Permission。 |
| 删除用户权限 | `erpnext.users.delete_user_permission` | 确认执行 | `L5_ADMIN` | 明确确认后删除 User Permission。 |

尚未覆盖：

- 密码重置
- API key / API secret 轮换
- 强制登出 / session 撤销
- DocShare 创建、更新、删除专用工具
- Role / Role Profile 的写入生命周期
- 实际写入 DocPerm / Custom DocPerm 的工具
- 批量权限矩阵审计

## Assets / 资产

当前覆盖范围：

```text
Asset, Asset Category, Asset Location,
Asset Movement, Asset Maintenance, Asset Maintenance Log,
Asset Repair, Asset Value Adjustment,
Asset Depreciation Schedule
```

| ERPNext 功能 | ToolCall | 控制级别 | 风险 | 当前能力 |
| --- | --- | --- | --- | --- |
| 查询资产 | `erpnext.assets.search_assets` | 读取 | `L0` | 按公司、资产分类、位置、状态、物料、保管人或名称查询 Asset。 |
| 查询资产分类 | `erpnext.assets.search_asset_categories` | 读取 | `L0` | 查询 Asset Category。 |
| 查询资产位置 | `erpnext.assets.search_asset_locations` | 读取 | `L0` | 查询 Asset Location。 |
| 资产财务快照 | `erpnext.assets.get_financial_snapshot` | 读取 | `L0` | 读取采购价值、财务账簿、折旧上下文和可选折旧计划。 |
| 折旧计划查看 | `erpnext.assets.get_depreciation_schedule` | 读取 | `L0` | 列出 Asset Depreciation Schedule 和可选到期折旧行，不做折旧过账。 |
| 创建资产草稿 | `erpnext.assets.create_asset_draft` | 草稿写入 | `L3` | 创建 `docstatus = 0` 的 Asset 草稿。 |
| 创建资产移动草稿 | `erpnext.assets.create_movement_draft` | 草稿写入 | `L3` | 创建资产转移、领用、接收类 Asset Movement 草稿。 |
| 创建资产维护计划草稿 | `erpnext.assets.create_maintenance_draft` | 草稿写入 | `L3` | 创建 Asset Maintenance 草稿。 |
| 创建资产维护日志草稿 | `erpnext.assets.create_maintenance_log_draft` | 草稿写入 | `L3` | 创建 Asset Maintenance Log 草稿。 |
| 创建资产维修草稿 | `erpnext.assets.create_repair_draft` | 草稿写入 | `L3` | 创建 Asset Repair 草稿。 |
| 创建资产价值调整草稿 | `erpnext.assets.create_value_adjustment_draft` | 草稿写入 | `L3` | 创建 Asset Value Adjustment 草稿；提交属于财务高风险。 |
| 准备资产处置/出售 | `erpnext.assets.prepare_disposal_or_sale` | 预览 | `L1` | 读取资产上下文并返回后续动作，不做 GL 过账、不创建发票。 |
| 提交资产单据 | `erpnext.assets.submit_document` | 确认执行 | `L4` / `L5_FINANCIAL` | 明确确认后提交支持的资产生命周期单据；Asset 和 Value Adjustment 属于财务高风险。 |

尚未覆盖：

- ERPNext 页面按钮封装，例如 make movement、make invoice、scrap、restore、depreciation entry
- 折旧过账
- 资产出售发票创建
- 资产处置/报废过账
- 维护上下文 helper
- 维修成本上下文 helper
- 不同版本中 Asset Location / Location 的兼容适配

## Stock / 库存

当前覆盖范围：

```text
Item integration, Warehouse, Bin, Stock Settings,
Stock Entry, Stock Reconciliation, Batch, Serial No,
Pick List, Stock Reservation Entry, Item Reorder,
Quality Inspection, Stock Ledger Entry,
Delivery Note / Purchase Receipt stock impact review
```

| ERPNext 功能 | ToolCall | 控制级别 | 风险 | 当前能力 |
| --- | --- | --- | --- | --- |
| 库存余额 | `erpnext.stock.get_balance` | 读取 | `L0` | 按物料和/或仓库读取 Bin 库存余额。 |
| 物料库存位置 | `erpnext.stock.get_item_locations` | 读取 | `L0` | 查询某个已解析 Item 在哪些仓库/Bin 有库存。 |
| 库存流水 | `erpnext.stock.get_ledger_entries` | 读取 | `L0` | 读取 Stock Ledger Entry 审计行。 |
| 库存设置 | `erpnext.stock.get_stock_settings` | 读取 | `L0` | 读取 Stock Settings 单例。 |
| 解析物料 | `erpnext.stock.resolve_item` | 预览 | `L1` | 使用可选 PostgreSQL 物料库和 ERPNext Item 搜索解析用户输入的物料描述。 |
| 创建库存移动草稿 | `erpnext.stock.create_entry_draft` | 草稿写入 | `L3` | 创建 Stock Entry 草稿，不提交库存移动。 |
| 创建库存盘点/调整草稿 | `erpnext.stock.create_reconciliation_draft` | 草稿写入 | `L3` | 创建 Stock Reconciliation 草稿；提交会改变数量/价值。 |
| 查询批次 | `erpnext.stock.search_batches` | 读取 | `L0` | 按物料或关键词查询 Batch。 |
| 批次余额 | `erpnext.stock.list_batch_balances` | 读取 | `L0` | 按物料、批次、仓库和库存流水汇总批次可用量。 |
| 查询序列号 | `erpnext.stock.search_serial_numbers` | 读取 | `L0` | 按物料、仓库、状态或关键词查询 Serial No。 |
| 创建批次 | `erpnext.stock.create_batch` | 草稿 / 主数据写入 | `L3` | 创建 Batch 追溯记录，不移动库存。 |
| 更新批次 | `erpnext.stock.update_batch` | 确认执行 | `L4` | 明确确认后更新 Batch 追溯记录。 |
| 创建序列号 | `erpnext.stock.create_serial_no` | 草稿 / 主数据写入 | `L3` | 创建 Serial No 追溯记录，不移动库存。 |
| 更新序列号 | `erpnext.stock.update_serial_no` | 确认执行 | `L4` | 明确确认后更新 Serial No。 |
| 查询拣货单 | `erpnext.stock.list_pick_lists` | 读取 | `L0` | 查询 Pick List。 |
| 创建拣货单草稿 | `erpnext.stock.create_pick_list_draft` | 草稿写入 | `L3` | 创建 Pick List 草稿，提交是单独的高风险动作。 |
| 查询库存预留 | `erpnext.stock.list_reservations` | 读取 | `L0` | 查询 Stock Reservation Entry。 |
| 创建库存预留草稿 | `erpnext.stock.create_reservation_draft` | 草稿写入 | `L3` | 创建 Stock Reservation Entry 草稿；提交会影响可用库存。 |
| 库存估值预览 | `erpnext.stock.preview_valuation` | 预览 | `L1` | 通过 agent_bridge 预览数量/价值影响，不创建库存单据。 |
| 缺料分配预览 | `erpnext.stock.allocate_shortages` | 预览 | `L1` | 预览可用库存和短缺，不创建预留、拣货或采购请求。 |
| 查询发货单 | `erpnext.stock.list_delivery_notes` | 读取 | `L0` | 从库存角度查看 Delivery Note；销售模块拥有业务流程。 |
| 查询采购收货 | `erpnext.stock.list_purchase_receipts` | 读取 | `L0` | 从库存角度查看 Purchase Receipt；采购模块拥有业务流程。 |
| 单据库存影响 | `erpnext.stock.get_document_impact` | 读取 | `L0` | 读取 Delivery Note 或 Purchase Receipt 及其库存流水影响。 |
| 物料补货规则 | `erpnext.stock.list_item_reorders` | 读取 | `L0` | 读取补货阈值和补货数量。 |
| 质量检验 | `erpnext.stock.list_quality_inspections` | 读取 | `L0` | 读取 Quality Inspection。 |
| 查询仓库 | `erpnext.stock.list_warehouses` | 读取 | `L0` | 查询 Warehouse。 |
| 创建仓库 | `erpnext.stock.create_warehouse` | 草稿 / 主数据写入 | `L3` | 创建 Warehouse 主数据，不移动库存。 |
| 更新仓库 | `erpnext.stock.update_warehouse` | 草稿 / 主数据写入 | `L3` | 更新 Warehouse 主数据，不移动库存。 |
| 查询物料分组 | `erpnext.stock.list_item_groups` | 读取 | `L0` | 查询 Item Group。 |
| 创建物料分组 | `erpnext.stock.create_item_group` | 草稿 / 主数据写入 | `L3` | 创建 Item Group 主数据。 |
| 更新物料分组 | `erpnext.stock.update_item_group` | 草稿 / 主数据写入 | `L3` | 更新 Item Group 主数据。 |
| 查询 UOM | `erpnext.stock.list_uoms` | 读取 | `L0` | 查询 UOM。 |
| 创建 UOM | `erpnext.stock.create_uom` | 草稿 / 主数据写入 | `L3` | 创建 UOM 主数据。 |
| 更新 UOM | `erpnext.stock.update_uom` | 草稿 / 主数据写入 | `L3` | 更新 UOM 主数据。 |
| 提交库存单据 | `erpnext.stock.submit_document` | 确认执行 | `L4` | 明确确认后提交库存影响单据。 |

尚未覆盖：

- 库存移动前影响预检，包括负库存、仓库、批次、序列号、UOM、过账日期校验
- 基于实盘数量的盘点差异预览
- 序列号自动选择
- 拣货位置建议
- 库存预留预览/释放
- 基于 projected/reserved/ordered 数量的补货计划预览
- 本地创建并提交真实库存移动的 smoke 测试

## Buying / 采购

当前覆盖范围：

```text
Supplier, Supplier Group, Supplier Scorecard,
Material Request, Request for Quotation,
Supplier Quotation, Purchase Order, Purchase Receipt,
Item Supplier, Item Price, Buying Settings,
Purchase Analytics
```

| ERPNext 功能 | ToolCall | 控制级别 | 风险 | 当前能力 |
| --- | --- | --- | --- | --- |
| 查询供应商 | `erpnext.buying.search_suppliers` | 读取 | `L0` | 查询 Supplier，包括采购 warning/prevention 字段。 |
| 供应商评分卡 | `erpnext.buying.search_supplier_scorecards` | 读取 | `L0` | 读取 Supplier Scorecard 和 RFQ/PO warn/prevent 标记。 |
| 供应商采购画像 | `erpnext.buying.get_supplier_procurement_profile` | 预览 | `L1` | 读取 Supplier、scorecard、可选 Item Supplier 和 Item Price，返回 RFQ/PO 是否允许、警告或阻断。 |
| 创建供应商分组 | `erpnext.buying.create_supplier_group_draft` | 草稿 / 主数据写入 | `L3` | 创建 Supplier Group 草稿/主数据。 |
| 创建供应商 | `erpnext.buying.create_supplier_draft` | 草稿 / 主数据写入 | `L3` | 创建 Supplier 主数据，不创建采购交易。 |
| 创建采购申请草稿 | `erpnext.buying.create_material_request_draft` | 草稿写入 | `L3` | 物料解析后创建 Purchase Material Request 草稿。 |
| 创建询价单草稿 | `erpnext.buying.create_request_for_quotation_draft` | 草稿写入 | `L3` | 创建带供应商行和已解析物料的 Request for Quotation 草稿。 |
| 创建供应商报价草稿 | `erpnext.buying.create_supplier_quotation_draft` | 草稿写入 | `L3` | 创建 Supplier Quotation 草稿。 |
| 创建采购订单草稿 | `erpnext.buying.create_purchase_order_draft` | 草稿写入 | `L3` | 创建 Purchase Order 草稿，不提交采购承诺。 |
| 创建采购收货草稿 | `erpnext.buying.create_purchase_receipt_draft` | 草稿写入 | `L3` | 创建 Purchase Receipt 草稿，不提交库存移动。 |
| 采购建议 | `erpnext.buying.generate_purchase_suggestions` | 读取 / 分析 | `L0` | 通过 agent_bridge 业务方法生成低库存采购建议。 |
| 查询物料供应商 | `erpnext.buying.search_item_suppliers` | 读取 | `L0` | 查询 Item Supplier。 |
| 查询采购价格 | `erpnext.buying.search_item_prices` | 读取 | `L0` | 按物料、价格表、供应商、币种和有效期查询 buying Item Price。 |
| 采购设置 | `erpnext.buying.get_buying_settings` | 读取 | `L0` | 读取 Buying Settings 单例。 |
| 采购分析 | `erpnext.buying.run_purchase_analysis` | 读取 / 报表 | `L0` | 通过标准报表工具运行采购分析报表。 |
| 供应商报价比较 | `erpnext.buying.compare_supplier_quotations` | 预览 | `L1` | 比较 Supplier Quotation 总价和行价格；不中标、不创建 PO。 |
| 提交采购单据 | `erpnext.buying.submit_document` | 确认执行 | `L4` | 明确确认后提交 Material Request、RFQ、Supplier Quotation、Purchase Order 或 Purchase Receipt。 |

尚未覆盖：

- Supplier Scorecard 刷新/写入
- RFQ 邮件预览/发送
- Material Request 到 RFQ 的 mapper
- RFQ 到 Supplier Quotation 的 mapper
- Supplier Quotation 到 Purchase Order 的 mapper
- 报价中标流程
- MR 到 PO/PR 的完整本地采购 smoke 测试

## Accounting / 财务

当前覆盖范围：

```text
Account, Cost Center, Budget, Fiscal Year,
Accounting Period, Payment Terms, Tax Templates,
General Ledger, AR/AP, Financial Reports,
Journal Entry, Payment Entry, Sales Invoice,
Purchase Invoice, Period Closing Voucher,
Bank Reconciliation
```

| ERPNext 功能 | ToolCall | 控制级别 | 风险 | 当前能力 |
| --- | --- | --- | --- | --- |
| 查询会计科目 | `erpnext.accounting.search_accounts` | 读取 | `L0` | 查询 chart of accounts。 |
| 查询成本中心 | `erpnext.accounting.search_cost_centers` | 读取 | `L0` | 查询成本中心树。 |
| 查询预算 | `erpnext.accounting.search_budgets` | 读取 | `L0` | 查询 Budget。 |
| 查询财政年度 | `erpnext.accounting.search_fiscal_years` | 读取 | `L0` | 查询 Fiscal Year。 |
| 查询会计期间 | `erpnext.accounting.search_accounting_periods` | 读取 | `L0` | 按公司/日期重叠查询 Accounting Period。 |
| 查询付款条件 | `erpnext.accounting.search_payment_terms` | 读取 | `L0` | 查询 Payment Term 或 Payment Terms Template。 |
| 查询税模板 | `erpnext.accounting.search_tax_templates` | 读取 | `L0` | 查询销售/采购税费模板。 |
| 报表过滤器契约 | `erpnext.accounting.get_report_filters` | 读取 | `L0` | 读取标准报表需要哪些过滤器，不运行报表。 |
| 总账 | `erpnext.accounting.general_ledger` | 读取 / 报表 | `L0` | 使用校验后的过滤器运行 General Ledger。 |
| 应收账款 | `erpnext.accounting.accounts_receivable` | 读取 / 报表 | `L0` | 运行 Accounts Receivable。 |
| 应付账款 | `erpnext.accounting.accounts_payable` | 读取 / 报表 | `L0` | 运行 Accounts Payable。 |
| 财务报表 | `erpnext.accounting.financial_report` | 读取 / 报表 | `L0` | 运行 Trial Balance、Balance Sheet、Profit and Loss Statement 或 Cash Flow。 |
| 创建会计凭证草稿 | `erpnext.accounting.create_journal_entry_draft` | 草稿写入 | `L3` | 创建 Journal Entry 草稿，不过账。 |
| 创建付款单草稿 | `erpnext.accounting.create_payment_entry_draft` | 草稿写入 | `L3` | 创建 Payment Entry 草稿，不提交付款。 |
| 创建销售发票草稿 | `erpnext.accounting.create_sales_invoice_draft` | 草稿写入 | `L3` | 创建 Sales Invoice 草稿，不提交发票。 |
| 创建采购发票草稿 | `erpnext.accounting.create_purchase_invoice_draft` | 草稿写入 | `L3` | 创建 Purchase Invoice 草稿，不提交发票。 |
| 创建期末结转凭证草稿 | `erpnext.accounting.create_period_closing_voucher_draft` | 草稿写入 | `L3` | 创建 Period Closing Voucher 草稿，不提交期末结转。 |
| 付款分配准备 | `erpnext.accounting.prepare_payment_allocation` | 预览 | `L1` | 准备 Payment Entry 引用分配，不创建付款。 |
| 发票税费准备 | `erpnext.accounting.prepare_invoice_taxes` | 预览 | `L1` | 准备税费行和估算税额；最终发票草稿仍由 ERPNext 校验。 |
| 银行对账准备 | `erpnext.accounting.prepare_bank_reconciliation` | 预览 | `L1` | 收集 Bank Transaction 和 Payment Entry 候选，不匹配、不过账。 |
| 应用银行对账 | `erpnext.accounting.apply_bank_reconciliation` | 确认执行 | `L5_FINANCIAL` | 财务确认后，把已有付款单据匹配到 Bank Transaction；不创建新的付款/JV。 |
| 创建预算草稿 | `erpnext.accounting.create_budget_draft` | 草稿写入 | `L3` | 创建 Budget 草稿。 |
| 更新预算草稿 | `erpnext.accounting.update_budget_draft` | 草稿写入 | `L3` | 更新 Budget 草稿并强制 `docstatus = 0`。 |
| 提交财务单据 | `erpnext.accounting.submit_financial_document` | 确认执行 | `L5_FINANCIAL` | 明确确认后提交支持的 GL 影响财务单据。 |

尚未覆盖：

- ERPNext 服务端 Payment Entry builder 预览
- 从付款分配结果创建 Payment Entry 的 helper
- 服务端发票税费/总额预览
- 从源单据创建发票草稿
- 银行对账候选评分
- 从 Bank Transaction 创建付款/JV 草稿
- Budget Variance 报表 wrapper
- 期末结账 readiness 检查
- cancel/amend/workflow/budget submit 的财务生命周期 wrapper

## 重要解释

这个矩阵表示：

```text
这些功能已经有专用的、模块化的 ToolCall。
```

它不表示：

```text
ERPNext 的每个按钮、每条工作流边界、每个服务端 controller 动作
都已经实现了完整 parity。
```

当前工具层最强的是：

- 读取、查询、报表
- 权限和财务风险显式化
- 草稿创建
- 显式确认门
- 一部分预览 helper
- 面向 Agent Runtime 的稳定 ToolResult 结构

下一步开发重点是继续把更多 ERPNext 页面动作变成专用 ToolCall 或
`agent_bridge` wrapper，尤其是那些用通用 CRUD 太危险或会丢失业务逻辑的动作。

