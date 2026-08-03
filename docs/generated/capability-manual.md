# Capability 说明书目录

目录版本：`manual-efdb8130f9e448fa`

## 采购

采购需求、询价、下单、收货与退货。

先确定员工要处理的采购阶段，再沿 contains 关系加载具体能力。

## 材料申请

把项目用料需求整理为材料申请。

用于提出项目用料需求。先加载创建操作，再提交项目、物料描述、数量和需求日期。

## 创建材料申请草稿

解析真实项目、仓库和物料后创建采购类型材料申请草稿。

提供项目、物料、数量和需求日期。公司、仓库、物料编码与单位由 Nexterp 解析；信息完整后 prepare 会返回不可修改的确认摘要。

## 询价

从已提交材料申请向一家或多家真实供应商发起询价。

先加载 从材料申请创建询价草稿 操作节点，再按说明提交业务事实。

## 供应商报价

依据已提交询价记录某一家供应商的报价。

先加载 从询价创建供应商报价草稿 操作节点，再按说明提交业务事实。

## 采购订单

从有效的已提交供应商报价生成采购订单。

先加载 从供应商报价创建采购订单草稿 操作节点，再按说明提交业务事实。

## 采购收货

从已提交采购订单记录实际到货。

先加载 从采购订单创建收货草稿 操作节点，再按说明提交业务事实。

## 采购退货

从已提交采购收货生成整单或部分退货。

先加载 从采购收货创建退货草稿 操作节点，再按说明提交业务事实。

## 创建材料申请草稿字段槽位

| 序号 | 字段 | 来源 | 控件 | 目标 |
|---:|---|---|---|---|
| 1 | 公司 | runtime_context | read_only | `arguments.company` |
| 2 | 项目 | runtime_context | select | `context.erpnext_project` |
| 3 | 收货仓库 | runtime_context | select | `context.warehouse` |
| 4 | 交货日期 | user_input | date | `arguments.schedule_date` |
| 5 | 物料编码 | resolver | search_select | `arguments.items[].item_code` |
| 6 | 数量 | user_input | number | `arguments.items[].qty` |
| 7 | 计量单位 | user_choice | select | `arguments.items[].uom` |
| 8 | 明细项目 | derived | derived | `arguments.items[].project` |
| 9 | 明细仓库 | derived | derived | `arguments.items[].warehouse` |
| 10 | 明细需求日期 | derived | derived | `arguments.items[].schedule_date` |
| 11 | 申请类型 | fixed | fixed | `arguments.material_request_type` |

### 业务规则

- **至少一个明细**：请至少选择一种物料。
- **数量为正数**：每个物料的数量必须大于 0。
- **业务主键已解析**：公司、项目、仓库和物料必须来自真实数据。
- **需求日期有效**：需求日期必须使用 YYYY-MM-DD。

## 从材料申请创建询价草稿字段槽位

| 序号 | 字段 | 来源 | 控件 | 目标 |
|---:|---|---|---|---|
| 1 | 来源材料申请 | source_document | search_select | `source.material_request` |
| 2 | 询价供应商 | user_choice | search_select | `arguments.suppliers` |
| 3 | 下单日期 | system_generated | read_only | `arguments.transaction_date` |
| 4 | 交货日期 | source_document | read_only | `arguments.schedule_date` |
| 5 | 询价明细 | source_document | read_only | `arguments.items` |
| 6 | 给供应商的说明 | user_input | select | `arguments.message_for_supplier` |

### 业务规则

- **来源材料申请已提交**：只有已提交的采购材料申请可以转询价。
- **供应商已解析**：至少选择一家真实供应商。
- **来源关系保留**：每个询价明细必须保留材料申请来源行。

## 从询价创建供应商报价草稿字段槽位

| 序号 | 字段 | 来源 | 控件 | 目标 |
|---:|---|---|---|---|
| 1 | 来源询价单 | source_document | search_select | `source.request_for_quotation` |
| 2 | 报价供应商 | user_choice | search_select | `arguments.supplier` |
| 3 | 报价明细 | user_input | number | `arguments.items` |
| 4 | 报价有效期 | user_input | date | `arguments.valid_till` |
| 5 | 币种 | user_choice | select | `arguments.currency` |
| 6 | 下单日期 | system_generated | read_only | `arguments.transaction_date` |

### 业务规则

- **来源询价已提交**：只有已提交询价可以生成供应商报价。
- **供应商唯一**：一张供应商报价只能对应一家供应商。
- **报价非负**：报价单价不能小于 0。

## 从供应商报价创建采购订单草稿字段槽位

| 序号 | 字段 | 来源 | 控件 | 目标 |
|---:|---|---|---|---|
| 1 | 来源供应商报价 | source_document | search_select | `arguments.supplier_quotation` |
| 2 | 下单明细 | user_choice | select | `arguments.selected_items` |
| 3 | 交货日期 | user_input | date | `arguments.schedule_date` |
| 4 | 下单日期 | system_generated | read_only | `arguments.transaction_date` |

### 业务规则

- **供应商报价已提交**：采购订单只能从已提交报价生成。
- **报价仍有效**：已过有效期的报价不能直接下单。
- **可转数量足够**：下单数量不得超过报价剩余可转数量。
- **报价来源保留**：采购订单明细必须保留供应商报价来源行。

## 从采购订单创建收货草稿字段槽位

| 序号 | 字段 | 来源 | 控件 | 目标 |
|---:|---|---|---|---|
| 1 | 来源采购订单 | source_document | search_select | `arguments.purchase_order` |
| 2 | 本次收货明细 | user_choice | select | `arguments.selected_items` |
| 3 | 退货日期 | user_input | date | `arguments.posting_date` |
| 4 | 收货仓库 | user_choice | search_select | `arguments.selected_items[].warehouse` |

### 业务规则

- **采购订单已提交**：只有已提交采购订单可以收货。
- **未收数量足够**：本次收货数量不得超过订单未收数量。
- **订单来源保留**：收货明细必须保留采购订单来源行。

## 从采购收货创建退货草稿字段槽位

| 序号 | 字段 | 来源 | 控件 | 目标 |
|---:|---|---|---|---|
| 1 | 来源采购收货 | source_document | search_select | `arguments.purchase_receipt` |
| 2 | 是否整单退货 | user_input | select | `arguments.full_return` |
| 3 | 退货明细 | user_choice | select | `arguments.items` |
| 4 | 退货日期 | user_input | date | `arguments.posting_date` |
| 5 | 退货原因 | user_input | select | `arguments.reason` |

### 业务规则

- **采购收货已提交**：只有已提交采购收货可以退货。
- **退货范围明确**：必须明确整单退货或部分退货明细。
- **可退数量足够**：退货数量不得超过当前可退数量。
- **退货来源保留**：退货单必须保留 return_against 和来源明细。
