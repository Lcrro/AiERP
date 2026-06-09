# ERPNext Capability Map

This document is the first local capability map for the Nexterp Agent project.
It records what ERPNext can do at the module level, so later we can connect each
business capability to DocTypes, ToolCalls, and agent_bridge business methods.

Stage 1 goal:

```text
用户说人话
  -> Agent 翻译成 ToolCall
  -> 系统执行 ToolCall
  -> ERPNext 返回结果
  -> Agent 再翻译成人话
```

For that loop to work well, the Agent needs this kind of map:

```text
ERPNext 模块
  -> 主要业务功能
  -> 核心 DocType
  -> 员工常见动作
  -> 可用 ToolCall
  -> 是否需要 agent_bridge 封装
  -> 风险等级
```

## Module Overview

| 模块 | 主要功能 |
| --- | --- |
| Accounting / 财务 | 会计科目、总账、应收应付、付款、银行、税、预算、财务报表 |
| Procurement / Buying / 采购 | 供应商、采购申请、询价、供应商报价、采购订单、采购收货 |
| Sales / 销售 | 客户、报价、销售订单、发货、销售发票、信用额度、销售团队 |
| CRM | 线索、商机、客户互动、销售机会跟进 |
| Stock / 库存 | 物料、仓库、库存余额、库存移动、批次、序列号、库存盘点 |
| Manufacturing / 生产 | BOM、工单、生产计划、作业卡、物料需求 |
| Projects / 项目 | 项目、任务、里程碑、工时、延期跟踪 |
| Assets / 资产 | 固定资产、折旧、资产维护、资产移动、报废 |
| Point of Sale / POS | 零售收银、POS 发票、门店销售 |
| Quality / 质量 | 质量检查、质量标准、检验流程 |
| Support / 客服支持 | Issue、工单、客户问题、服务响应 |
| HR & Payroll | 员工、人事、考勤、薪资，具体取决于是否安装 HRMS |
| No-Code Builder / 自定义 | 自定义 DocType、字段、表单、报表、工作流 |
| Data Management | 数据导入、导出、批量更新、备份 |
| Users & Permissions | 用户、角色、权限、字段权限、共享、访问日志 |

## How Agents Should Use This Map

The table above is not a final tool list. It is the business-language entrypoint
that helps us decide what the Agent should do when an employee speaks naturally.

Examples:

| 员工表达 | 可能模块 | 可能动作 |
| --- | --- | --- |
| 帮我看一下哪些客户快断货了 | Sales、Stock、CRM | 查客户销售历史、查库存、生成跟进任务 |
| 把低于安全库存的物料整理一下 | Stock、Buying | 查库存余额、查补货规则、生成采购建议 |
| 今天有哪些应收快到期 | Accounting、Sales | 查应收账款、按客户或销售负责人分组 |
| 这个项目有哪些延期风险 | Projects | 查任务、里程碑、工时、延期状态 |
| 给这个客户创建报价 | Sales | 创建 Quotation 草稿，必要时查价格、库存、信用 |

## Next Enrichment

This document should be expanded by the DocType indexer.

Planned generated fields:

| 字段 | 说明 |
| --- | --- |
| core_doctypes | 该模块最核心的 DocType，例如 Customer、Sales Order、Item、Bin |
| important_fields | Agent 需要理解的关键字段 |
| child_tables | 子表结构，例如 Sales Order Item |
| is_submittable | 是否支持 submit/cancel/amend 生命周期 |
| permissions | 当前角色可读、可写、可提交、可取消的能力 |
| common_toolcalls | 推荐 Agent 使用的 ToolCall |
| bridge_methods | 需要 agent_bridge 封装的复杂业务动作 |
| risk_level | read、write、submit、financial、admin 等风险等级 |

## Working Rule

Generic CRUD tools are enough for simple document operations, but they should not
be the only interface for complex ERP work.

Use this rule when designing Agent actions:

```text
简单查、建、改、删
  -> ERPNext Adapter 通用工具

跨 DocType、涉及业务判断、需要稳定口径
  -> agent_bridge 业务方法

提交、取消、付款、发票、权限、系统设置等高风险动作
  -> 后续监管层确认或审批
```

