# 基础主数据标准 v0.1

本文定义除物料以外的企业基础主数据治理口径。物料主数据以 `data/material_master/release_v1_0/material_master_release_v1_0.tsv` 为唯一发布入口。

## 目标

先在项目内维护一套干净、可审查、可重建的企业基础资料表，再导入新的 ERPNext 测试账套。

```text
基础主数据表
  -> 校验主键、外键、状态和导入顺序
  -> 生成 ERPNext 导入包
  -> 新建干净测试账套
  -> 按顺序导入公司、组织、人员、项目、仓库、供应商、价格和期初库存
  -> 再跑 Agent / ToolCall 沙盘
```

## 范围

第一版覆盖“小型土木公司一日运转模拟”需要的主数据：

| 领域 | 主数据 | ERPNext 目标 |
|---|---|---|
| 组织 | 公司、部门、岗位画像 | Company、Department、Role / Role Profile |
| 人员 | 员工、任职关系、测试登录账号 | Employee、Employee Assignment / Custom DocType、User |
| 项目 | 项目、项目团队、成本中心 | Project、Project User、Cost Center |
| 仓库 | 中心仓、项目仓 | Warehouse |
| 采购 | 供应商、联系人、供应商供货策略 | Supplier、Contact、Item Price / Supplier Item |
| 财务 | 付款条件、价目表 | Payment Terms Template、Price List |
| 库存 | 期初库存 | Stock Entry |

不在本阶段做：

- 真实公司生产数据。
- ERPNext 生产账套写入。
- 复杂会计科目体系重构。
- 权限策略最终版。
- 客户、销售、合同等后续模块的完整主数据。

## 表设计原则

### 1. 使用自己的稳定编码

每张表必须有一个稳定主键，例如：

```text
company_code
department_code
employee_code
project_code
warehouse_code
supplier_code
```

这些编码不等于 ERPNext 自动编号。导入时可以映射到 ERPNext `name`、`title` 或自定义字段。

### 2. 人看得懂，系统也能导

每张表同时保留：

- 业务名称：给人审查。
- 稳定编码：给脚本和导入器使用。
- ERPNext 映射字段：给后续导入做准备。
- `status` 和 `note`：记录是否可用、是否候选、是否需要确认。

项目表额外保留 `project_short_name`。项目全称用于合同、ERPNext 正式项目名和财务归集；项目简称用于员工对话、筛选、看板和 Agent Resolver，例如 `南京一期`、`泰和1.2标`。

组织架构采用 `公司本部 -> UP事业部 -> 项目/基地管理口` 的管理树。`departments.tsv` 只表达人员和管理口径，不替代 `projects.tsv` 中的正式 Project；例如 `合流1.3标项目部` 是组织口径，`PRJ-HL-13` 才是业务单据、成本、仓库和 Agent 上下文使用的项目主数据。

项目运行状态独立记录在 `projects.tsv.project_operating_status`，不要和 `status` 混用。`status=active` 表示主数据启用；`project_operating_status` 表示业务状态，例如 `在建`、`储备`、`基地运营`。当前口径是：合流1.3标为在建，蕰川路基地为基地运营，其他项目先作为储备项目。

当前项目仓库规则：每个项目一个默认仓库，仓库名称为 `项目简称 + 仓库`，例如 `竹白1.2标仓库`。项目默认仓库写入 `projects.tsv.default_warehouse_code`，仓库本体写入 `warehouses.tsv`，两者必须一一对应。

仓库负责人优先引用已存在的 `employees.tsv.employee_code`。如果负责人来自推测，必须在 `warehouses.tsv.note` 标明“按现有名单推测”；如果只有姓名但员工编码尚未落表，先不要硬填不存在的编码。

员工多组织/多项目任职关系写入 `employee_assignments.tsv`。`employees.tsv` 只保存一个人的主档案；如果同一个人在 UP事业部、项目或基地兼任不同岗位，不重复创建员工，而是在任职关系表里增加多条记录。登录后选择项目上下文时优先读取这张表。

### 3. 物料只引用，不重复

供应商价格和期初库存只引用物料发布表里的 `item_code`：

```text
data/material_master/release_v1_0/material_master_release_v1_0.tsv
```

不在基础主数据表里重复维护 `sku_name`、规格、物料族等物料本体信息。

### 4. 先导基础，再导交易

基础主数据导入顺序必须固定：

```text
公司
  -> 部门 / 岗位 / 成本中心 / 仓库
  -> 项目
  -> 员工 / 任职关系 / 用户 / 项目团队
  -> 供应商 / 联系人
  -> 付款条件 / 价目表 / 供应商供货策略
  -> 期初库存
```

材料申请、采购订单、收货、发票、付款、领料等交易单据不属于基础主数据。

## 当前表入口

```text
data/master_data/release_v0_1/
```

核心表：

```text
manifest.tsv
companies.tsv
departments.tsv
role_profiles.tsv
employees.tsv
employee_assignments.tsv
user_accounts.tsv
projects.tsv
project_teams.tsv
warehouses.tsv
cost_centers.tsv
suppliers.tsv
supplier_contacts.tsv
payment_terms.tsv
price_lists.tsv
supplier_item_policies.tsv
stock_opening_balances.tsv
```

## 后续校验规则

后续应增加脚本检查：

- 每张表主键唯一。
- 外键存在，例如员工部门必须存在、项目经理必须存在、仓库负责人必须存在。
- `supplier_item_policies.tsv` 和 `stock_opening_balances.tsv` 中的 `item_code` 必须存在于物料发布表。
- 导入顺序符合 `manifest.tsv`。
- `status` 只能是 `active`、`candidate`、`disabled`。
- 测试账号不包含明文密码。

## ERPNext 导入策略

第一阶段只生成表，不写 ERPNext。

第二阶段生成导入包：

- ERPNext Data Import 用 CSV。
- 或通过 Adapter / agent_bridge 调用 DocType API 创建。
- 所有写入必须可重复执行，重复执行不造重复数据。

第三阶段新建干净测试账套后导入：

```text
基础主数据
  -> 物料发布表
  -> 供应商价格
  -> 期初库存
  -> 一日事件流交易数据
```

这样我们能把“主数据准备”和“业务流程测试”拆开，出问题时更容易定位。
