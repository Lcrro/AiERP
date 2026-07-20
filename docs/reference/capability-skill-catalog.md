# Capability Skill 清单

当前共 20 项，发现时受员工岗位与底层 Tool 权限过滤。标记“写”的能力必须经过 Capability 编译和用户确认，不能通过通用 `execute_tool` 绕过。

| 模块 | Capability ID | 用途 | 类型 |
| --- | --- | --- | --- |
| 采购 | `material_request.create` | 创建采购类型材料申请草稿 | 写 |
| 采购 | `rfq.from_material_request` | 材料申请转询价 | 写 |
| 采购 | `supplier_quotation.from_rfq` | 从询价录入供应商报价 | 写 |
| 采购 | `supplier_quotation.compare` | 比较已提交供应商报价 | 读 |
| 采购 | `purchase_order.from_supplier_quotation` | 报价转采购订单 | 写 |
| 采购 | `purchase_order.from_material_request` | 材料申请直接转采购订单 | 写 |
| 采购 | `purchase_receipt.from_purchase_order` | 采购订单转收货 | 写 |
| 采购 | `purchase_return.from_receipt` | 收货单转采购退货 | 写 |
| 库存 | `stock.balance.query` | 查询实时库存 | 读 |
| 库存 | `stock.transfer.create` | 创建仓库调拨草稿 | 写 |
| 库存 | `stock.project_issue.create` | 创建项目领料草稿 | 写 |
| 库存 | `stock.reconciliation.create` | 创建库存盘点调整草稿 | 写 |
| 财务 | `finance.accounts_payable.query` | 查询应付账款 | 读 |
| 财务 | `finance.purchase_invoice.from_receipt` | 收货生成采购发票 | 写 |
| 财务 | `finance.supplier_payment.from_invoice` | 采购发票生成付款草稿 | 写 |
| 财务 | `finance.document.cancel` | 取消并冲销财务单据 | 写 |
| 项目 | `project.cost.query` | 查询项目成本 | 读 |
| 项目 | `project.exceptions.query` | 查询项目异常 | 读 |
| 项目 | `project.task.create` | 创建项目任务 | 写 |
| 项目 | `project.task.update` | 更新项目任务 | 写 |

完整 Guide 和 JSON Schema 由 `CapabilityRegistry` 从 Python/Pydantic 声明生成，不另建 YAML，避免两份事实来源。

真实 DeepSeek 稳定性基准：

```powershell
python scripts/acceptance/capability_runtime_stability.py --rounds 4
```

默认运行 5 个场景各 4 次，只执行查询或写入预览，不确认写单。报告保存到 `data/runtime/capability_runtime_stability_report.json`。
