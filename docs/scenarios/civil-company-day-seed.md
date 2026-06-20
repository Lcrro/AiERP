# 小型土木公司一日运转模拟：Sandbox 初始化

本文记录一日运转模拟在本地 ERPNext sandbox 中需要的基础数据。用途是让后续 ToolCall runner 可以反复执行同一套业务沙盘，而不是每次手工建项目、仓库、供应商和初始库存。

关联文档：

- [员工角色表](civil-company-day-roles.md)
- [时间顺序事件流](civil-company-day-events.md)
- [ToolCall 覆盖矩阵](civil-company-day-toolcall-coverage.md)
- [一天事件流准备度](civil-company-day-readiness.md)

## 初始化脚本

脚本位置：

```powershell
scripts\seed_civil_company_scenario.py
```

默认使用本地 ERPNext profile：

```powershell
python scripts\seed_civil_company_scenario.py --profile civil
```

写入本地 sandbox：

```powershell
python scripts\seed_civil_company_scenario.py --profile civil --apply
```

跳过初始库存写入：

```powershell
python scripts\seed_civil_company_scenario.py --profile civil --apply --skip-stock
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
| 城东道路改造项目 | PROJ-0001 |
| 南区排水管网项目 | PROJ-0002 |
| 西站配套设施项目 | PROJ-0003 |

供应商：

| 供应商 | 类型 |
|---|---|
| SCEN-CIVIL 安科劳保用品 | 劳保用品 |
| SCEN-CIVIL 通达管材 | 管材管件 |
| SCEN-CIVIL 强盛建材 | 建材 |
| SCEN-CIVIL 恒信电气 | 电气材料 |

沙盘 seed 会在干净站点中补齐少量测试主数据：

- UOM：`双`、`个`、`米`、`袋`、`卷`、`套`、`件`、`根`
- Item Group：`劳保用品`、`电气材料`、`建材`、`管材管件`、`周转材料`
- Supplier Group：`经销商`、`原材料`、`电气`
- Item：`SAFE-000005`、`SAFE-000006`、`SAFE-000007`、`ELEC-000001`、`ELEC-000002`、`ELEC-000005`、`ELEC-000006`、`ELEC-000007`、`MAT-CEM-000004`、`PIPE-000415`、`PIPE-000021`、`PIPE-000019`、`PIPE-000416`、`MAT-CAST-000001`、`MAT-000159`、`METAL-000001`

## 采购价格

seed 会为 16 个沙盘物料创建 `Standard Buying` 的 `Item Price`，用于采购员在 09:30 汇总材料申请、10:00 直接下常用品采购订单、10:30 判断哪些材料需要询价。

| 物料 | 默认供应商 | 单位 | 单价 |
|---|---|---|---:|
| SAFE-000005 帆布手套 | SCEN-CIVIL 安科劳保用品 | 双 | 8 |
| SAFE-000006 安全帽 | SCEN-CIVIL 安科劳保用品 | 个 | 28 |
| SAFE-000007 反光背心 | SCEN-CIVIL 安科劳保用品 | 件 | 18 |
| ELEC-000005 PVC电工胶布 | SCEN-CIVIL 恒信电气 | 卷 | 4 |
| ELEC-000002 热缩管 | SCEN-CIVIL 恒信电气 | 米 | 3 |
| ELEC-000001 漏电保护器 | SCEN-CIVIL 恒信电气 | 个 | 380 |
| ELEC-000006 电缆线 | SCEN-CIVIL 恒信电气 | 米 | 35 |
| ELEC-000007 LED灯管 | SCEN-CIVIL 恒信电气 | 根 | 24 |
| MAT-CEM-000004 水泥 | SCEN-CIVIL 强盛建材 | 袋 | 35 |
| PIPE-000415 PVC排水管 | SCEN-CIVIL 通达管材 | 米 | 18 |
| PIPE-000021 PVC弯头 | SCEN-CIVIL 通达管材 | 个 | 6 |
| PIPE-000019 PVC直接 | SCEN-CIVIL 通达管材 | 个 | 8 |
| PIPE-000416 PVC三通 | SCEN-CIVIL 通达管材 | 个 | 12 |
| MAT-CAST-000001 球墨铸铁井盖 | SCEN-CIVIL 通达管材 | 套 | 420 |
| MAT-000159 移动脚手架 | SCEN-CIVIL 强盛建材 | 套 | 180 |
| METAL-000001 角钢 | SCEN-CIVIL 强盛建材 | 米 | 16 |

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
SCEN-CIVIL-SEED-STOCK-CENTER-V2
SCEN-CIVIL-SEED-STOCK-PROJECT-V2
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
| SAFE-000006 | 80 | 28 |
| SAFE-000007 | 120 | 18 |
| ELEC-000007 | 30 | 24 |
| PIPE-000416 | 20 | 12 |
| MAT-CAST-000001 | 6 | 420 |
| METAL-000001 | 80 | 16 |

项目仓初始库存：

| 物料 | 数量 | 单价 |
|---|---:|---:|
| SAFE-000005 | 50 | 8 |
| ELEC-000005 | 12 | 4 |
| MAT-CEM-000004 | 20 | 35 |
| PIPE-000415 | 60 | 18 |
| SAFE-000006 | 12 | 28 |
| SAFE-000007 | 20 | 18 |

## 开工前背景异常

为 08:00 管理层摘要准备 5 条开放 `ToDo`，全部带 `SCEN-CIVIL-PREP-*` 标记：

| 标记 | 业务含义 | 负责人 | 关联 |
|---|---|---|---|
| `SCEN-CIVIL-PREP-MANAGER-LOW-STOCK` | 项目仓电气物料库存偏低 | 王海 | 西站配套设施项目 |
| `SCEN-CIVIL-PREP-PO-DELAY-RISK` | 通达管材到货延期风险 | 袁芳 | 通达管材 |
| `SCEN-CIVIL-PREP-AP-DUE-RISK` | 强盛建材历史应付款今日到期 | 刘敏 | 强盛建材 |
| `SCEN-CIVIL-PREP-RETURN-RISK` | 劳保用品历史型号不符，今日收货需重点核对 | 曹瑞 | 安科劳保用品 |
| `SCEN-CIVIL-PREP-APPROVAL-QUEUE` | 项目经理 09:10 前需统一确认材料需求 | 李志远 | 城东道路改造项目 |

这些 ToDo 是沙盘背景输入，不代表当天新产生的业务单据。

## 流程策略

seed 报告中会写入 `process_policies`，用于 Wizard 或 Agent Runtime 判断下一步：

| 事件 | 策略 |
|---|---|
| 09:30 | 采购按项目、物料分组、供应商和紧急程度汇总待处理材料申请。 |
| 10:00 | 劳保用品、电气常用耗材、水泥等有固定采购价格的低风险物料，可生成采购订单草稿。 |
| 10:30 | 管材、井盖、钢材等规格复杂或价格波动物料，优先走询价和供应商报价。 |
| 13:30 | 采购收货原则上从已提交采购订单创建，保留源单据行引用。 |
| 14:00 | 到货不符先记录评论和 ToDo；只有已提交采购收货单才能生成退货草稿。 |
| 14:30 | 项目领料通过库存出库草稿，必须带项目、源仓库、物料、数量和成本中心。 |

## 验证要点

脚本成功写入后，应满足：

```text
failed_total = 0
```

重复执行 `--apply` 后，应看到主要动作变成 `skip_existing_*`，表示不会重复造数。

后续一日事件流 runner 应直接复用这些对象，不再临时创建公司、项目、仓库、供应商和员工。

当前 clean site 验证结果：

```text
Item = 16
Item Price = 16
ToDo = 5
Stock Entry = 4
Material Request / Purchase Order / Purchase Receipt / Purchase Invoice = 0
```

也就是说，基础数据和开工前异常已经准备好，但当天正式产生的采购、收货、发票单据仍保持为空，方便按时间顺序逐条测试。

## 事件流 Runner

runner 位置：

```powershell
scripts\run_civil_company_day_scenario.py
```

默认 dry-run 会执行只读 ToolCall，并跳过会创建草稿的写入 ToolCall：

```powershell
python scripts\run_civil_company_day_scenario.py --profile civil
```

创建草稿单据时必须显式加 `--apply`：

```powershell
python scripts\run_civil_company_day_scenario.py --profile civil --apply
```

运行结果写入：

```text
data/scenario/civil_company_day_run_report.json
```

runner 第一版用于验证 ToolCall 链路，不提交采购申请、采购订单、采购收货、库存出库或财务单据。提交类动作仍需要单独确认策略。
