# 字段槽位与操作模板模型

更新日期：`2026-07-22`

## 目的

Agent 不再把一整个 ERPNext ToolCall 当作需要一次猜完的 JSON。每个操作先展开为一组可复用字段槽位，再由 Runtime 根据明确来源填充、校验和编译。

```text
业务能力
→ 操作模板
→ 字段槽位及业务规则
→ 确定性 ToolCall
→ ToolGateway
→ ERPNext
```

首个纵向样板：

```text
op.material_request.create
→ material_request.create
→ erpnext.buying.create_material_request_draft
```

## 关系模型

### information_slot

定义可跨操作复用的业务事实。例如公司、项目、仓库、物料编码、数量和需求日期。`slot_id` 是稳定契约，数字序号只用于界面排序和人工沟通。

### operation_template

定义一个员工可理解的局部操作，以及最终对应的底层 ToolCall。一个 Capability 可以引用多个 Operation Template。

### operation_slot

连接操作与字段槽位，并保存该字段在本操作中的：

- 顺序和目标 JSON 路径。
- 是否必填。
- 来源类型。
- Resolver、固定值或派生来源。
- 本操作特有约束。
- 员工看到的控件类型：只读、查表选择、检索选择、日期、数值、派生或固定。
- 是否允许员工修改、关联的 ERPNext DocType、默认策略和格式提示。

同一个字段槽位在不同操作中可以有不同来源和必填规则。

### operation_rule

保存跨字段业务不变量，例如至少一个明细、数量必须为正数、Link 主键必须解析、需求日期格式有效。

PostgreSQL DDL 位于：

```text
config/operation_catalog_schema.sql
```

## 字段来源

```text
user_input       员工必须说明
user_choice      从真实候选中选择
runtime_context  当前身份、项目或仓库上下文
resolver         查询真实主数据并返回主键
source_document  从来源单据继承
erp_default      由 ERPNext 默认值处理
system_generated 单号、创建时间等系统字段
derived          从已确认槽位派生
fixed            操作模板固定值
```

模型只负责理解员工表达和辅助选择。项目、仓库、物料编码等 Link 字段仍必须由 Resolver 或 ERPNext 结果提供。

样板页面使用本地主数据发布表模拟 ERPNext 查询：项目来自 `Project`，仓库随项目过滤，物料来自 `Item` 检索，单位随物料加载。正式 Runtime 中由 Resolver/ERPNext API 提供同一选项接口，字段槽位契约不变。

## 材料申请样板

`op.material_request.create` 当前包含 11 个槽位：

```text
01 公司
02 项目
03 目标仓库
04 需求日期
05 物料编码
06 数量
07 计量单位
08 明细项目
09 明细仓库
10 明细需求日期
11 申请类型
```

其中 08–10 从已经确认的单据级槽位派生，11 固定为 `Purchase`。Runtime 不需要再次询问员工。

本地可视化样板：

```text
http://127.0.0.1:8788/operation-model
```

## 下一步

1. 用真实 Project、Warehouse、Item Resolver 填充样板，而不是页面模拟值。
2. 将现有采购编译器的字段来源迁入 Catalog，避免两份事实来源。
3. 增加局部修改操作：改单据日期、改明细数量、增删明细、提交工作流。
4. 为操作节点建立复用关系，一个字段槽位可以被多个操作引用。
5. 完成材料申请纵向验证后，再扩展询价、采购订单、收货和退货。
