# Capability 说明书目录

目录版本：`manual-f51ff39d816997c2`

## 采购

采购需求、询价、下单、收货与退货。

先确定员工要处理的采购阶段，再沿 contains 关系加载具体能力。

## 材料申请

把项目用料需求整理为材料申请。

用于提出项目用料需求。先加载创建操作，再提交项目、物料描述、数量和需求日期。

## 创建材料申请草稿

解析真实项目、仓库和物料后创建采购类型材料申请草稿。

提供项目、物料、数量和需求日期。公司、仓库、物料编码与单位由 Nexterp 解析；信息完整后 prepare 会返回不可修改的确认摘要。

## 字段槽位

| 序号 | 字段 | 来源 | 控件 | 目标 |
|---:|---|---|---|---|
| 1 | 公司 | runtime_context | read_only | `arguments.company` |
| 2 | 项目 | runtime_context | select | `context.erpnext_project` |
| 3 | 目标仓库 | runtime_context | select | `context.warehouse` |
| 4 | 需求日期 | user_input | date | `arguments.schedule_date` |
| 5 | 物料编码 | resolver | search_select | `arguments.items[].item_code` |
| 6 | 数量 | user_input | number | `arguments.items[].qty` |
| 7 | 计量单位 | user_choice | select | `arguments.items[].uom` |
| 8 | 明细项目 | derived | derived | `arguments.items[].project` |
| 9 | 明细仓库 | derived | derived | `arguments.items[].warehouse` |
| 10 | 明细需求日期 | derived | derived | `arguments.items[].schedule_date` |
| 11 | 申请类型 | fixed | fixed | `arguments.material_request_type` |

## 业务规则

- **至少一个明细**：请至少选择一种物料。
- **数量为正数**：每个物料的数量必须大于 0。
- **业务主键已解析**：公司、项目、仓库和物料必须来自真实数据。
- **需求日期有效**：需求日期必须使用 YYYY-MM-DD。
