# 基础主数据

这个目录保存除物料以外的企业基础主数据。它和 `data/material_master/` 是平级关系：

- `material_master/` 管物料、SKU、物料检索。
- `master_data/` 管公司、组织、员工、项目、仓库、供应商、付款条件、价目表、期初库存等业务底座。

当前入口：

```text
data/master_data/release_v0_1/
```

## 当前目标

第一版服务当前 UP 事业部、项目和蕰川路基地，表结构按后续真实公司上线可扩展的方式设计。我们先维护自己的表，确认稳定后再导入独立 ERPNext 开发账套。

## 使用原则

- 当前目录只保存可审查、可复用的主数据表，不直接写 ERPNext。
- 表里的 `*_code` 是我们自己的稳定编码，不依赖 ERPNext 自动编号。
- 导入 ERPNext 时再把这些编码映射到 `Company`、`Department`、`Employee`、`User`、`Project`、`Warehouse`、`Supplier` 等 DocType。
- 物料只引用 `data/material_master/release_v1_0/material_master_release_v1_0.tsv` 的 `item_code`，不在这里重复维护物料本体。
- 期初库存、供应商价格、项目团队都视为可重建的初始化数据，不混入物料主表。
- 供应商当前采用“候选品类供应商”口径，只用于让采购策略和测试流程可运行，不代表真实合作供应商。
- 库存当前采用“零库存初始化”口径，`stock_opening_balances.tsv` 中 `qty=0` 且 `valuation_rate=0`；参考价格放在 `supplier_item_policies.tsv`，不形成期初库存金额。

## release_v0_1 表清单

| 文件 | 主要内容 | ERPNext 映射 |
|---|---|---|
| `manifest.tsv` | 表清单、导入顺序和依赖 | 导入编排 |
| `companies.tsv` | 公司主体 | Company |
| `departments.tsv` | 部门和组织结构 | Department |
| `role_profiles.tsv` | 岗位画像和 ERPNext 角色映射 | Role / Role Profile |
| `employees.tsv` | 员工、岗位、默认项目和仓库 | Employee |
| `employee_assignments.tsv` | 员工多组织/多项目任职关系，支持登录后选择项目上下文 | Employee Assignment / Custom DocType |
| `user_accounts.tsv` | 测试登录账号 | User |
| `projects.tsv` | 项目主数据 | Project |
| `project_teams.tsv` | 项目班组和项目角色 | Project / Project User |
| `warehouses.tsv` | 仓库主数据 | Warehouse |
| `cost_centers.tsv` | 成本中心 | Cost Center |
| `suppliers.tsv` | 供应商 | Supplier |
| `supplier_contacts.tsv` | 供应商联系人 | Contact |
| `payment_terms.tsv` | 付款条件 | Payment Terms Template |
| `price_lists.tsv` | 采购价目表 | Price List |
| `supplier_item_policies.tsv` | 供应商-物料供货策略 | Item Price / Supplier Item |
| `stock_opening_balances.tsv` | 期初库存 | Stock Entry |

## 下一步

1. 继续补齐项目、仓库、供应商和价格策略。
2. 做校验脚本，检查主键唯一、外键存在、物料编码存在。
3. 生成 ERPNext 导入包。
4. 新建干净测试账套后按 `manifest.tsv` 顺序导入。

派生表使用以下命令统一生成：

```powershell
python scripts\master_data\build_material_master_release_v1.py
python scripts\master_data\finalize_master_data_release.py
python scripts\master_data\validate_master_data_release.py
```

## 校验

```powershell
python scripts\master_data\validate_master_data_release.py
```

校验内容：

- TSV 列数一致。
- 主键不为空且不重复。
- `status` 只使用 `active`、`candidate`、`disabled`。
- 部门、员工、项目、仓库、供应商等外键存在。
- 供应商供货策略和期初库存引用的 `item_code` 存在于物料发布版 v0.3。
