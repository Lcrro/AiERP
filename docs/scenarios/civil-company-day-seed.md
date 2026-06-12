# 小型土木公司一日运转模拟：Sandbox 初始化

本文记录一日运转模拟在本地 ERPNext sandbox 中需要的基础数据。用途是让后续 ToolCall runner 可以反复执行同一套业务沙盘，而不是每次手工建项目、仓库、供应商和初始库存。

关联文档：

- [员工角色表](civil-company-day-roles.md)
- [时间顺序事件流](civil-company-day-events.md)
- [ToolCall 覆盖矩阵](civil-company-day-toolcall-coverage.md)

## 初始化脚本

脚本位置：

```powershell
scripts\seed_civil_company_scenario.py
```

默认使用本地 ERPNext profile：

```powershell
python scripts\seed_civil_company_scenario.py --profile local
```

写入本地 sandbox：

```powershell
python scripts\seed_civil_company_scenario.py --profile local --apply
```

跳过初始库存写入：

```powershell
python scripts\seed_civil_company_scenario.py --profile local --apply --skip-stock
```

运行结果写入：

```text
data/scenario/civil_company_seed_report.json
```

脚本是幂等的。已经存在的项目、仓库、供应商、用户和初始库存凭证会被跳过，不会重复创建。

## 已初始化的数据

公司：

```text
STEC (Demo)
```

仓库：

| 业务名称 | ERPNext 仓库 |
|---|---|
| 中心仓 | SCEN-CIVIL 中心仓 - SD |
| 项目仓 | SCEN-CIVIL 项目仓 - SD |

项目：

| 业务名称 | ERPNext 项目 |
|---|---|
| 城东道路改造项目 | PROJ-0004 |
| 南区排水管网项目 | PROJ-0005 |
| 西站配套设施项目 | PROJ-0006 |

供应商：

| 供应商 | 类型 |
|---|---|
| SCEN-CIVIL 安科劳保用品 | 劳保用品 |
| SCEN-CIVIL 通达管材 | 管材管件 |
| SCEN-CIVIL 强盛建材 | 建材 |
| SCEN-CIVIL 恒信电气 | 电气材料 |

测试用户：

| 姓名 | 职位 | ERPNext User |
|---|---|---|
| 陈建国 | 总经理 | chen.jianguo@scen-civil.local |
| 刘敏 | 财务主管 | liu.min@scen-civil.local |
| 赵强 | 采购主管 | zhao.qiang@scen-civil.local |
| 孙丽 | 行政采购员 | sun.li@scen-civil.local |
| 王海 | 仓库主管 | wang.hai@scen-civil.local |
| 周鹏 | 项目仓管员 | zhou.peng@scen-civil.local |
| 李志远 | 项目经理 | li.zhiyuan@scen-civil.local |
| 马超 | 施工班组长 | ma.chao@scen-civil.local |
| 黄伟 | 项目经理 | huang.wei@scen-civil.local |
| 郭亮 | 施工班组长 | guo.liang@scen-civil.local |
| 何珊 | 项目经理 | he.shan@scen-civil.local |
| 邓凯 | 机电班组长 | deng.kai@scen-civil.local |
| 袁芳 | 供应商联络员 | yuan.fang@scen-civil.local |
| 曹瑞 | 质检员 | cao.rui@scen-civil.local |
| 许峰 | 系统管理员 | xu.feng@scen-civil.local |

这些用户默认 `enabled = 0`，用于业务上下文和后续权限测试，不用于真实登录。

## 初始库存

脚本创建并提交两张 `Material Receipt` 类型的 `Stock Entry`，用 `remarks` 标记避免重复创建：

```text
SCEN-CIVIL-SEED-STOCK-CENTER
SCEN-CIVIL-SEED-STOCK-PROJECT
```

中心仓初始库存：

| 物料 | 数量 | 单价 |
|---|---:|---:|
| SAFE-000005 | 300 | 8 |
| ELEC-000005 | 60 | 4 |
| ELEC-000002 | 120 | 3 |
| ELEC-000001 | 4 | 380 |
| ELEC-000006 | 20 | 35 |
| MAT-CEM-000004 | 80 | 35 |
| PIPE-000415 | 200 | 18 |
| PIPE-000021 | 40 | 6 |
| PIPE-000019 | 30 | 8 |
| MAT-000159 | 6 | 180 |

项目仓初始库存：

| 物料 | 数量 | 单价 |
|---|---:|---:|
| SAFE-000005 | 50 | 8 |
| ELEC-000005 | 12 | 4 |
| MAT-CEM-000004 | 20 | 35 |
| PIPE-000415 | 60 | 18 |

## 验证要点

脚本成功写入后，应满足：

```text
failed_total = 0
```

重复执行 `--apply` 后，应看到主要动作变成 `skip_existing_*`，表示不会重复造数。

后续一日事件流 runner 应直接复用这些对象，不再临时创建公司、项目、仓库、供应商和员工。

## 事件流 Runner

runner 位置：

```powershell
scripts\run_civil_company_day_scenario.py
```

默认 dry-run 会执行只读 ToolCall，并跳过会创建草稿的写入 ToolCall：

```powershell
python scripts\run_civil_company_day_scenario.py --profile local
```

创建草稿单据时必须显式加 `--apply`：

```powershell
python scripts\run_civil_company_day_scenario.py --profile local --apply
```

运行结果写入：

```text
data/scenario/civil_company_day_run_report.json
```

runner 第一版用于验证 ToolCall 链路，不提交采购申请、采购订单、采购收货、库存出库或财务单据。提交类动作仍需要单独确认策略。
