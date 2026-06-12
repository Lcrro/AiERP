# ERPNext 项目专项 ToolCall 覆盖

范围：Projects / 项目专项。

这个文档记录第一批面向项目业务的 ToolCall。它们不是裸库存工具的重复，
而是把项目、成本中心、仓库可用量和领料草稿放在同一个业务语境里。

## 核心 DocType

| 能力 | ERPNext DocType |
| --- | --- |
| 项目主数据和上下文 | `Project` |
| 项目任务上下文 | `Task` |
| 项目领料 | `Stock Entry`, `Stock Entry Detail` |
| 项目采购收货上下文 | `Purchase Receipt` |
| 项目领料成本验证 | `Stock Entry`, `Stock Ledger Entry` |

## 已实现工具

| Tool | ERPNext 表面 | 风险 | 说明 |
| --- | --- | --- | --- |
| `erpnext.projects.get_project_cost_context` | `Project`, `Task`, `Stock Entry`, `Purchase Receipt` | `L0` | 读取项目成本上下文和相关记录，不创建或提交单据。 |
| `erpnext.projects.get_material_issue_context` | `Project`, `Bin` | `L1` | 按项目、来源仓库和领料行预览库存是否足够。 |
| `erpnext.projects.create_material_issue_draft` | `Stock Entry` | `L3` | 创建 `Material Issue` 类型 Stock Entry 草稿，把 project/cost_center 写入明细行，不提交库存移动。 |
| `erpnext.projects.verify_material_issue_cost_impact` | `Stock Entry`, `Stock Ledger Entry` | `L0` | 读取已提交项目领料单据和库存流水，汇总领料数量、成本中心、项目和库存价值影响。 |

## 项目领料规则

项目领料不直接等同于 `erpnext.stock.create_entry_draft`。

项目专项 wrapper 会做这些事情：

- 先读取 Project。
- 带入项目公司和成本中心上下文。
- 创建草稿前检查来源仓库可用库存。
- 默认遇到缺料就阻断，不创建草稿。
- 在 Stock Entry 明细行写入 `project` 和 `cost_center`。

提交领料草稿仍然要单独调用 `erpnext.stock.submit_document`，并提供库存确认信息。

提交后可以调用 `erpnext.projects.verify_material_issue_cost_impact` 复核：

- Stock Entry 是否为 `Material Issue`
- 明细行是否带项目和成本中心
- 出库数量和明细金额
- Stock Ledger Entry 中的出库数量和价值影响

## 尚未实现

- 项目预算和实际成本差异报表 wrapper。
- 项目退料 / 剩料回库业务 ToolCall。
- 项目任务级领料校验。
- 项目仓库和班组绑定规则。
- 工时、外包、机械台班、费用报销等非库存项目成本归集。

## 测试

单元测试文件：

```powershell
python -m pytest tests\unit\erpnext\test_projects_tools.py -q
```
