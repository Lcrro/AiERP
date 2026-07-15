# 当前 ToolCall 清单

本文档是当前代码中 ERPNext ToolCall 的中文快照，来源于 `src/nexterp_agent/erpnext/tool_registry.py` 导出的 `ERPNext_TOOL_SCHEMAS`，并校验 `ERPNextAdapter.handlers`。

它回答一个很实际的问题：现在 Agent Runtime 可以向 Adapter 发哪些结构化工具调用。

## 总览

- 生成时间：2026-07-15
- Tool schema 数：151
- Adapter handler 数：151
- schema 有但 handler 缺失：[]
- handler 有但 schema 缺失：[]

## 按模块统计

| 模块 | 数量 |
| --- | ---: |
| 通用 ERP、Agent 与协作 | 30 |
| 用户与权限 | 18 |
| 资产 | 13 |
| 库存 | 38 |
| 采购 | 23 |
| 财务 | 25 |
| 项目 | 4 |

## 按风险等级统计

| 风险等级 | 数量 | 含义 |
| --- | ---: | --- |
| `L0` | 72 | 只读查询，不改变 ERPNext 数据。 |
| `L1` | 12 | 解析、预览、建议、上下文准备，不直接写业务单据。 |
| `L2` | 5 | 低风险协作写入，例如评论、ToDo、附件、差异记录。 |
| `L3` | 43 | 创建或更新草稿、主数据草稿、库存/采购/财务草稿。 |
| `L4` | 11 | 提交、取消、删除、工作流执行等会改变单据状态的动作。 |
| `L5_ADMIN` | 6 | 高风险账号、角色、权限管理动作。 |
| `L5_FINANCIAL` | 2 | 高风险财务入账、对账或财务状态动作。 |

## 工具清单

说明：`必填参数` 来自当前 schema 的 `required` 字段；完整参数结构以代码中的 tool schema 为准。

### 通用 ERP、Agent 与协作

| ToolCall | 风险 | 必填参数 | 中文说明 |
| --- | --- | --- | --- |
| `erpnext.get_logged_user` | `L0` | - | 返回当前 API 会话对应的 ERPNext 用户。 |
| `erpnext.search_documents` | `L0` | `doctype` | 按 DocType、过滤条件、字段、分页和排序搜索 ERPNext 单据。 |
| `erpnext.search_items` | `L0` | `query` | 按编码、名称、别名/原始名、规格和分组搜索标准化物料主数据，返回候选、分数、原因、状态和追问信息。 |
| `erpnext.count_documents` | `L0` | `doctype` | 统计某个 DocType 在可选过滤条件下的记录数量。 |
| `erpnext.get_document` | `L0` | `doctype`, `name` | 按 DocType 和单据名称读取一张 ERPNext 单据。 |
| `erpnext.create_document` | `L3` | `doctype`, `data` | 创建一张新的 ERPNext 单据。 |
| `erpnext.update_document` | `L3` | `doctype`, `name`, `data` | 更新一张已有 ERPNext 单据。 |
| `erpnext.delete_document` | `L4` | `doctype`, `name` | 删除一张 ERPNext 单据。 |
| `erpnext.document_exists` | `L0` | `doctype`, `name` | 检查某个 ERPNext 单据是否存在。 |
| `erpnext.resolve_link` | `L0` | `doctype`, `query` | 为 Link 字段查找可选关联单据。 |
| `erpnext.validate_fields` | `L0` | `doctype`, `fields` | 在执行 ToolCall 前校验字段名是否存在于目标 DocType。 |
| `erpnext.get_doctype_schema` | `L0` | `doctype` | 读取 ERPNext DocType 元数据和字段结构。 |
| `erpnext.submit_document` | `L4` | `doctype`, `name` | 按 ERPNext 服务端规则提交一张可提交单据。 |
| `erpnext.cancel_document` | `L4` | `doctype`, `name` | 按 ERPNext 服务端规则取消一张已提交单据。 |
| `erpnext.amend_document` | `L4` | `doctype`, `name` | 基于已取消单据创建修订草稿。 |
| `erpnext.get_workflow_actions` | `L0` | `doctype`, `name` | 列出某张 ERPNext 单据当前可执行的工作流动作。 |
| `erpnext.apply_workflow` | `L4` | `doctype`, `name`, `action` | 对某张 ERPNext 单据执行一个工作流动作。 |
| `erpnext.run_report` | `L0` | `report_name` | 运行 ERPNext 查询报表或脚本报表，并返回规范化报表数据。 |
| `erpnext.setup_item_master` | `L3` | - | 创建物料主数据 v0.1 所需的 ERPNext Item 自定义字段，可重复执行。 |
| `erpnext.prepare_item_from_intent` | `L0` | `intent` | 根据物料意图做规则校验和规范化，不创建 ERPNext Item。 |
| `erpnext.create_item_from_intent` | `L3` | `intent` | 根据已通过规则校验的物料意图创建 ERPNext Item。 |
| `erpnext.create_todo` | `L2` | `description` | 创建一个 ToDo 跟进任务。 |
| `erpnext.add_comment` | `L2` | `reference_doctype`, `reference_name`, `content` | 给 ERPNext 单据添加评论。 |
| `erpnext.get_comments` | `L0` | `reference_doctype`, `reference_name` | 读取 ERPNext 单据的评论列表。 |
| `erpnext.assign_to` | `L2` | `doctype`, `name`, `assign_to` | 把 ERPNext 单据分配给一个或多个用户。 |
| `erpnext.clear_assignment` | `L3` | `doctype`, `name`, `assign_to` | 移除或关闭某张 ERPNext 单据的分配。 |
| `erpnext.attach_file` | `L2` | `doctype`, `name`, `file_path` | 把本地文件作为附件上传到 ERPNext 单据。 |
| `erpnext.list_attachments` | `L0` | `doctype`, `name` | 列出某张 ERPNext 单据的附件。 |
| `erpnext.delete_attachment` | `L4` | `file_name` | 按 File 单据名删除一个 ERPNext 附件。 |
| `erpnext.call_method` | `L1` | `method` | 调用已白名单允许的 Frappe 方法；有专用 ToolCall 时优先使用专用工具。 |

### 用户与权限

| ToolCall | 风险 | 必填参数 | 中文说明 |
| --- | --- | --- | --- |
| `erpnext.users.list_users` | `L0` | - | 只读列出 ERPNext 用户，返回安全的身份和状态字段。 |
| `erpnext.users.get_user_access_summary` | `L0` | `user` | 读取某个用户的角色、角色配置、直接用户权限和基础状态。 |
| `erpnext.users.list_roles` | `L0` | - | 只读列出 Role 角色记录。 |
| `erpnext.users.list_role_profiles` | `L0` | - | 只读列出 Role Profile 角色配置记录。 |
| `erpnext.users.preview_role_profile_roles` | `L0` | `role_profile` | 在分配前展开某个 Role Profile 包含的角色。 |
| `erpnext.users.list_user_permissions` | `L0` | - | 按用户、允许 DocType 或允许值查询 User Permission 记录。 |
| `erpnext.users.list_shared_documents` | `L0` | - | 查询某个用户或某张单据相关的 DocShare 共享记录。 |
| `erpnext.users.list_access_logs` | `L0` | - | 查询 Access Log，用于访问审计。 |
| `erpnext.users.list_activity_logs` | `L0` | - | 查询 Activity Log，用于活动审计。 |
| `erpnext.users.get_permission_metadata` | `L0` | `doctype` | 查看某个 DocType 的 DocPerm/Custom DocPerm 权限元数据。 |
| `erpnext.users.preview_effective_permissions` | `L0` | `user`, `doctype` | 根据权限元数据和直接 User Permission 预览某用户对某 DocType 的可能权限；不是服务端运行时精确判定。 |
| `erpnext.users.check_server_permission` | `L0` | `user`, `doctype`, `action` | 通过 agent_bridge 调用 Frappe 服务端权限引擎，检查某用户对 DocType/单据/动作的真实权限，并与预览结果对比。 |
| `erpnext.users.preview_permission_policy_change` | `L5_ADMIN` | `doctype`, `changes` | 只预览 DocPerm 风格权限变更的前后差异，不写入 ERPNext。 |
| `erpnext.users.create_user_draft` | `L5_ADMIN` | `email`, `first_name`, `confirmation` | 创建 User 主数据，默认禁用且不发送欢迎邮件；需要显式确认元数据。 |
| `erpnext.users.set_user_enabled` | `L5_ADMIN` | `user`, `enabled`, `confirmation` | 启用或禁用用户；需要显式确认元数据。 |
| `erpnext.users.assign_roles` | `L5_ADMIN` | `user`, `mode`, `roles`, `confirmation` | 替换、增加或移除用户角色；需要显式确认元数据。 |
| `erpnext.users.create_user_permission` | `L5_ADMIN` | `user`, `allow`, `for_value`, `confirmation` | 创建一条 User Permission 记录；需要显式确认元数据。 |
| `erpnext.users.delete_user_permission` | `L5_ADMIN` | `name`, `confirmation` | 按名称删除一条 User Permission 记录；需要显式确认元数据。 |

### 资产

| ToolCall | 风险 | 必填参数 | 中文说明 |
| --- | --- | --- | --- |
| `erpnext.assets.search_assets` | `L0` | - | 按公司、资产类别、位置、状态、Item、保管人或资产名只读搜索固定资产。 |
| `erpnext.assets.search_asset_categories` | `L0` | - | 只读搜索 Asset Category 资产类别。 |
| `erpnext.assets.search_asset_locations` | `L0` | - | 只读搜索 Asset Location 资产位置。 |
| `erpnext.assets.get_financial_snapshot` | `L0` | `asset` | 读取单个资产的采购、财务账簿、折旧和折旧计划状态；不计提折旧、不生成总账、不创建出售/报废单据。 |
| `erpnext.assets.get_depreciation_schedule` | `L0` | `asset` | 只读列出资产折旧计划，可选择展开到期计划行；不计提折旧。 |
| `erpnext.assets.create_asset_draft` | `L3` | `data` | 只创建 Asset 资产草稿；提交/资本化属于高风险财务动作。 |
| `erpnext.assets.create_movement_draft` | `L3` | `data` | 创建 Asset Movement 资产移动草稿，支持发出、接收或转移；提交是单独 L4 动作。 |
| `erpnext.assets.create_maintenance_draft` | `L3` | `data` | 创建 Asset Maintenance 资产维护计划草稿；提交是单独 L4 动作。 |
| `erpnext.assets.create_maintenance_log_draft` | `L3` | `data` | 创建 Asset Maintenance Log 资产维护记录草稿；提交是单独 L4 动作。 |
| `erpnext.assets.create_repair_draft` | `L3` | `data` | 创建 Asset Repair 资产维修草稿；提交后可能影响资产价值或成本，需要确认。 |
| `erpnext.assets.create_value_adjustment_draft` | `L3` | `data` | 创建 Asset Value Adjustment 资产价值调整草稿；提交属于高风险财务动作。 |
| `erpnext.assets.prepare_disposal_or_sale` | `L1` | `asset` | 只读准备资产报废或出售上下文，不生成总账或发票，返回下一步动作和风险信息。 |
| `erpnext.assets.submit_document` | `L4` | `doctype`, `name`, `confirmation` | 在显式高风险确认元数据存在后提交资产生命周期单据；资本化和价值调整属于 L5_FINANCIAL，移动/维护/维修属于 L4。 |

### 库存

| ToolCall | 风险 | 必填参数 | 中文说明 |
| --- | --- | --- | --- |
| `erpnext.stock.get_balance` | `L0` | - | 按物料和/或仓库读取 Bin 库存余额，返回数量与估值快照。 |
| `erpnext.stock.get_item_locations` | `L0` | - | 查找某个已解析物料在哪些仓库/Bin 中有库存。 |
| `erpnext.stock.get_ledger_entries` | `L0` | - | 读取 Stock Ledger Entry 库存流水，用于库存移动审计。 |
| `erpnext.stock.get_stock_settings` | `L0` | - | 读取 Stock Settings 单例，了解库存预留、批次、序列号和估值行为等控制规则。 |
| `erpnext.stock.resolve_item` | `L1` | `query` | 先用可选 PostgreSQL 物料目录召回，再查 ERPNext Item，解析一个库存物料；不修改 ERPNext。 |
| `erpnext.stock.create_entry_draft` | `L3` | `items` | 创建 Stock Entry 库存单草稿，支持收料、发料、调拨、生产或重包；提交是单独 L4 动作。 |
| `erpnext.stock.create_reconciliation_draft` | `L3` | `items` | 创建 Stock Reconciliation 库存盘点/调整草稿；提交会改变数量/价值，属于 L4。 |
| `erpnext.stock.search_batches` | `L0` | - | 按物料或批次关键词搜索 Batch 批次记录。 |
| `erpnext.stock.list_batch_balances` | `L0` | - | 按物料、批次、仓库和库存流水汇总批次可用量，不移动库存。 |
| `erpnext.stock.search_serial_numbers` | `L0` | - | 按物料、仓库、状态或序列号关键词搜索 Serial No 记录。 |
| `erpnext.stock.create_batch` | `L3` | `data` | 为已有 ERPNext Item 创建 Batch 批次追溯记录；不移动库存。 |
| `erpnext.stock.update_batch` | `L4` | `name`, `data`, `confirmation` | 更新 Batch 批次追溯记录；由于会影响库存追溯，属于 L4。 |
| `erpnext.stock.create_serial_no` | `L3` | `data` | 为已有 ERPNext Item 创建 Serial No 序列号追溯记录；不提交库存移动。 |
| `erpnext.stock.update_serial_no` | `L4` | `name`, `data`, `confirmation` | 更新 Serial No 序列号追溯记录；由于会影响库存追溯，属于 L4。 |
| `erpnext.stock.list_pick_lists` | `L0` | - | 只读列出 Pick List 拣货单，用于仓库拣货流程。 |
| `erpnext.stock.create_pick_list_draft` | `L3` | - | 为发货、物料调拨或生产流程创建 Pick List 拣货草稿；提交是单独 L4 动作。 |
| `erpnext.stock.list_reservations` | `L0` | - | 按物料、仓库、来源单据或状态列出 Stock Reservation Entry 库存预留。 |
| `erpnext.stock.create_reservation_draft` | `L3` | `warehouse`, `reserved_qty` | 为已解析物料和来源单据创建 Stock Reservation Entry 库存预留草稿；提交会影响可用库存。 |
| `erpnext.stock.preview_valuation` | `L1` | `items` | 通过 agent_bridge 预览库存数量/价值影响，不创建库存单或盘点单。 |
| `erpnext.stock.allocate_shortages` | `L1` | `items` | 通过 agent_bridge 预览可用库存分配和缺口数量，不创建预留、拣货单或采购申请。 |
| `erpnext.stock.list_delivery_notes` | `L0` | - | 只读列出 Delivery Note 发货单，用于库存影响检查；销售流程仍由销售模块负责。 |
| `erpnext.stock.list_purchase_receipts` | `L0` | - | 只读列出 Purchase Receipt 采购收货单，用于库存影响检查；采购流程仍由采购模块负责。 |
| `erpnext.stock.get_document_impact` | `L0` | `doctype`, `name` | 读取 Delivery Note 或 Purchase Receipt 的库存流水影响，不编辑也不创建跨模块单据。 |
| `erpnext.stock.list_item_reorders` | `L0` | - | 按物料、仓库或物料申请类型查看 Item Reorder 补货阈值。 |
| `erpnext.stock.list_quality_inspections` | `L0` | - | 列出与收货、发货或物料质量流程相关的 Quality Inspection 质量检验单。 |
| `erpnext.stock.create_quality_inspection_draft` | `L3` | - | 创建进货、出货或过程质量检验草稿；是否提交另行处理。 |
| `erpnext.stock.verify_purchase_receipt_stock_impact` | `L0` | `purchase_receipt` | 对照 Stock Ledger Entry 验证已提交采购收货的入库数量和库存价值影响。 |
| `erpnext.stock.get_item_lifecycle_summary` | `L0` | - | 跨 Item、采购收货明细、库存流水、质检、库存单明细和采购发票明细读取物料生命周期摘要。 |
| `erpnext.stock.list_warehouses` | `L0` | - | 按公司或名称关键词列出 Warehouse 仓库。 |
| `erpnext.stock.create_warehouse` | `L3` | `data` | 创建 Warehouse 仓库主数据；不移动库存。 |
| `erpnext.stock.update_warehouse` | `L3` | `name`, `data` | 更新 Warehouse 仓库主数据；不移动库存。 |
| `erpnext.stock.list_item_groups` | `L0` | - | 按父级、是否分组或名称关键词列出 Item Group 物料分组。 |
| `erpnext.stock.create_item_group` | `L3` | `data` | 创建 Item Group 物料分组主数据；不创建物料、不移动库存。 |
| `erpnext.stock.update_item_group` | `L3` | `name`, `data` | 更新 Item Group 物料分组主数据；不创建物料、不移动库存。 |
| `erpnext.stock.list_uoms` | `L0` | - | 按启用状态或名称关键词列出 UOM 计量单位。 |
| `erpnext.stock.create_uom` | `L3` | `data` | 创建 UOM 计量单位主数据；不影响现有库存余额。 |
| `erpnext.stock.update_uom` | `L3` | `name`, `data` | 更新 UOM 计量单位主数据；不影响现有库存余额。 |
| `erpnext.stock.submit_document` | `L4` | `doctype`, `name`, `confirmation` | 在显式高风险确认元数据存在后提交会影响库存的单据。 |

### 采购

| ToolCall | 风险 | 必填参数 | 中文说明 |
| --- | --- | --- | --- |
| `erpnext.buying.search_suppliers` | `L0` | - | 按供应商名称、分组或类型搜索 Supplier，返回采购流程安全字段。 |
| `erpnext.buying.search_supplier_scorecards` | `L0` | - | 只读搜索 Supplier Scorecard，并查看 RFQ/PO 警告或阻止标记。 |
| `erpnext.buying.get_supplier_procurement_profile` | `L1` | `supplier` | 读取供应商、评分卡、可选物料供应商和价格上下文，用于判断 RFQ/PO 应阻止、警告还是允许。 |
| `erpnext.buying.create_supplier_group_draft` | `L3` | `supplier_group_name` | 创建 Supplier Group 供应商分组主数据。 |
| `erpnext.buying.create_supplier_draft` | `L3` | `supplier_name` | 创建 Supplier 供应商主数据，不提交任何交易。 |
| `erpnext.buying.create_material_request_draft` | `L3` | `items` | 创建采购用途的 Material Request 物料申请草稿，物料行必须通过 ERPNext Item/物料搜索解析。 |
| `erpnext.buying.create_request_for_quotation_draft` | `L3` | `suppliers`, `items` | 创建 Request for Quotation 询价单草稿，包含供应商和已解析物料行。 |
| `erpnext.buying.create_supplier_quotation_draft` | `L3` | `supplier`, `items` | 根据供应商和已解析物料行创建 Supplier Quotation 供应商报价草稿。 |
| `erpnext.buying.create_purchase_order_draft` | `L3` | `supplier`, `items` | 创建 Purchase Order 采购订单草稿；不提交业务承诺。 |
| `erpnext.buying.create_purchase_order_from_material_request_draft` | `L3` | `material_request`, `supplier` | 从已提交 Material Request 创建 Purchase Order 草稿，并保留来源行引用。 |
| `erpnext.buying.create_purchase_receipt_draft` | `L3` | `supplier`, `items` | 为收到的采购物料创建 Purchase Receipt 采购收货草稿；不提交库存移动。 |
| `erpnext.buying.create_purchase_receipt_from_purchase_order_draft` | `L3` | `purchase_order` | 从已提交 Purchase Order 创建 Purchase Receipt 草稿，并保留来源行引用。 |
| `erpnext.buying.record_purchase_receipt_discrepancy` | `L2` | `purchase_receipt`, `description` | 通过评论和可选 ToDo 记录采购收货差异/规格不符；不提交、不退货、不改变库存。 |
| `erpnext.buying.get_purchase_receipt_return_context` | `L1` | `purchase_receipt` | 在创建供应商退货草稿前，预览已提交采购收货的可退行。 |
| `erpnext.buying.create_purchase_receipt_return_draft` | `L3` | `purchase_receipt` | 基于已有已提交采购收货创建 Purchase Receipt 退货草稿；不提交退货。 |
| `erpnext.buying.generate_purchase_suggestions` | `L0` | - | 通过 agent_bridge 业务逻辑生成低库存采购建议。 |
| `erpnext.buying.search_item_suppliers` | `L0` | - | 按父级物料或供应商搜索 Item Supplier 物料供应商记录。 |
| `erpnext.buying.search_item_prices` | `L0` | - | 按物料、价格清单、供应商、币种和有效期搜索采购 Item Price。 |
| `erpnext.buying.get_pending_procurement_items` | `L0` | - | 按当前 ERPNext 用户权限汇总已提交材料申请中尚未订购的需求行，并批量返回相关仓库库存。 |
| `erpnext.buying.get_buying_settings` | `L0` | - | 读取 Buying Settings 采购设置单例。 |
| `erpnext.buying.run_purchase_analysis` | `L0` | - | 通过规范化报表工具运行标准采购分析报表。 |
| `erpnext.buying.compare_supplier_quotations` | `L1` | `supplier_quotations` | 预览比较供应商报价总额和物料单价，不定标、不创建采购订单。 |
| `erpnext.buying.submit_document` | `L4` | `doctype`, `name`, `confirmation` | 在显式高风险确认元数据存在后提交采购单据。 |

### 财务

| ToolCall | 风险 | 必填参数 | 中文说明 |
| --- | --- | --- | --- |
| `erpnext.accounting.search_accounts` | `L0` | - | 按公司、账户类型、过滤条件、分页和排序只读搜索 Account 科目。 |
| `erpnext.accounting.search_cost_centers` | `L0` | - | 按公司、过滤条件、分页和排序只读搜索 Cost Center 成本中心。 |
| `erpnext.accounting.search_budgets` | `L0` | - | 按公司、会计年度、过滤条件、分页和排序只读搜索 Budget 预算。 |
| `erpnext.accounting.search_fiscal_years` | `L0` | - | 按年份、禁用状态、过滤条件、分页和排序只读搜索 Fiscal Year 会计年度。 |
| `erpnext.accounting.search_accounting_periods` | `L0` | - | 按公司、日期范围、过滤条件、分页和排序只读搜索 Accounting Period 会计期间。 |
| `erpnext.accounting.search_payment_terms` | `L0` | - | 只读搜索 Payment Term 或 Payment Terms Template 付款条件。 |
| `erpnext.accounting.search_tax_templates` | `L0` | - | 只读搜索销售或采购税费模板。 |
| `erpnext.accounting.get_report_filters` | `L0` | `report_name` | 返回标准财务报表支持的过滤参数契约，不运行报表。 |
| `erpnext.accounting.general_ledger` | `L0` | - | 运行 ERPNext 总账报表，并返回只读规范化结果。 |
| `erpnext.accounting.accounts_receivable` | `L0` | - | 运行 ERPNext 应收账款报表，并返回只读规范化结果。 |
| `erpnext.accounting.accounts_payable` | `L0` | - | 运行 ERPNext 应付账款报表，并返回只读规范化结果。 |
| `erpnext.accounting.financial_report` | `L0` | `report_name` | 运行允许的只读财务报表：试算表、资产负债表、利润表或现金流量表。 |
| `erpnext.accounting.create_journal_entry_draft` | `L3` | `data` | 只创建 Journal Entry 会计分录草稿；提交凭证是单独的高风险财务动作。 |
| `erpnext.accounting.create_payment_entry_draft` | `L3` | `data` | 只创建 Payment Entry 付款/收款草稿；提交付款是单独的高风险财务动作。 |
| `erpnext.accounting.create_sales_invoice_draft` | `L3` | `data` | 只创建 Sales Invoice 销售发票草稿；提交发票是单独的高风险财务动作。 |
| `erpnext.accounting.create_purchase_invoice_draft` | `L3` | `data` | 只创建 Purchase Invoice 采购发票草稿；提交发票是单独的高风险财务动作。 |
| `erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft` | `L3` | `purchase_receipt` | 从已提交采购收货创建采购发票草稿，保留来源行引用并检查可开票数量。 |
| `erpnext.accounting.create_period_closing_voucher_draft` | `L3` | `data` | 只创建 Period Closing Voucher 期间结转凭证草稿；提交结转是单独的高风险财务动作。 |
| `erpnext.accounting.prepare_payment_allocation` | `L1` | `party_type`, `party` | 为已提交销售/采购发票准备付款分摊引用，不创建也不提交付款。 |
| `erpnext.accounting.prepare_invoice_taxes` | `L1` | `invoice_type` | 从销售/采购税费模板或显式税费行准备发票税费行；最终金额仍由 ERPNext 在草稿创建时校验。 |
| `erpnext.accounting.prepare_bank_reconciliation` | `L1` | - | 汇总银行交易和付款凭证候选供对账复核，不执行匹配或入账。 |
| `erpnext.accounting.apply_bank_reconciliation` | `L5_FINANCIAL` | `bank_transaction`, `matches`, `confirmation` | 在财务显式确认后，通过 agent_bridge 将已有付款单据匹配到一条银行交易；不创建新付款或会计分录。 |
| `erpnext.accounting.create_budget_draft` | `L3` | `data` | 创建 Budget 预算草稿，并强制 docstatus=0；预算提交仍需单独复核。 |
| `erpnext.accounting.update_budget_draft` | `L3` | `name`, `data` | 更新 Budget 预算草稿，并强制 docstatus=0；不提交预算控制。 |
| `erpnext.accounting.submit_financial_document` | `L5_FINANCIAL` | `doctype`, `name`, `confirmation` | 在显式确认元数据存在后，提交会影响总账的财务单据。 |

### 项目

| ToolCall | 风险 | 必填参数 | 中文说明 |
| --- | --- | --- | --- |
| `erpnext.projects.get_project_cost_context` | `L0` | `project` | 从 Project、Task、Stock Entry 和 Purchase Receipt 读取项目成本上下文。 |
| `erpnext.projects.get_material_issue_context` | `L1` | `project`, `source_warehouse`, `items` | 在创建 Stock Entry 草稿前，预览项目领料需求与来源仓库可用量。 |
| `erpnext.projects.create_material_issue_draft` | `L3` | `project`, `source_warehouse`, `items` | 创建带项目和成本中心上下文的项目领料 Stock Entry 草稿；不提交库存移动。 |
| `erpnext.projects.verify_material_issue_cost_impact` | `L0` | `stock_entry` | 对照项目/成本中心明细和库存流水，验证已提交项目领料 Stock Entry 的数量与价值影响。 |
