# 项目状态

最后更新：2026-06-12

## 当前版本

- 当前整理版本：`project-structure-cleanup-v0.3`
- 当前分支：`codex/project-structure-cleanup-v0.3`
- 整理基线：`996ae1e`
- 本轮状态：工程结构整理已完成；在此基础上新增了采购退货、项目成本/项目领料、材料申请转采购订单、采购订单转采购收货、采购收货转采购发票、到货差异记录，以及物料生命周期验证类业务 ToolCall，并开始建立土木公司一日运转沙盘。项目结构第一轮收纳已完成：`scripts/` 已按职责分区并保留兼容入口，`data/` 已建立目标分区说明，`agent_runtime/` 与 `scenarios/` 已建立代码边界。

## 当前结构

- Tool schema 已拆到 `src/nexterp_agent/erpnext/tool_schemas/`。
- 风险推断已拆到 `src/nexterp_agent/erpnext/risk_policy.py`。
- `ERPNextAdapter` 已拆成薄主类加模块 mixin：
  - `modules/generic.py`
  - `modules/users.py`
  - `modules/assets.py`
  - `modules/stock.py`
  - `modules/buying.py`
  - `modules/projects.py`
  - `modules/accounting.py`
  - `modules/common.py`
- 测试目录已整理为：
  - `tests/unit/erpnext/`
  - `tests/unit/item_master/`
  - `tests/integration/`

## ToolCall 覆盖状态

当前注册状态：

```text
150 tool schemas
150 adapter handlers
missing = []
extra = []
```

五个重点模块与项目专项：

| 模块 | Tool 前缀 | Tool 数量 |
| --- | --- | ---: |
| 用户与权限 | `erpnext.users.*` | 18 |
| 资产 | `erpnext.assets.*` | 13 |
| 库存 | `erpnext.stock.*` | 38 |
| 采购 | `erpnext.buying.*` | 22 |
| 财务 | `erpnext.accounting.*` | 25 |
| 项目专项 | `erpnext.projects.*` | 4 |

## 测试入口

常用命令：

```powershell
python -m pytest tests\unit\erpnext -q
python -m pytest tests\unit\item_master -q
python -m pytest tests\integration -q
python -m pytest -q
```

本地 ERPNext sandbox 集成测试需要先加载 `.env` 中的 `NEXTERP_LOCAL_*` 凭据。

当前验证结果：

```text
注册表一致性：150 schemas / 150 handlers / missing=[] / extra=[]
无显式 .env 全量测试：140 passed, 3 skipped
加载本地 sandbox .env 全量测试：本轮未运行；上一轮为 100 passed
土木公司 ToolCall 覆盖检查：registered tools=150 / referenced tools=44 / missing=0
土木公司 runner dry-run：10 steps / 6 executed / 4 skipped_write / failed=0
土木公司 runner apply：10 steps / 10 executed / failed=0
采购模块单测：18 passed
库存模块单测：18 passed
项目专项单测：6 passed
采购/库存/项目/财务相关单测：61 passed
MR -> PO 本地 smoke：MAT-MR-2026-00005 -> PUR-ORD-2026-00024，PO 行保留 material_request/material_request_item/project
PO -> PR 本地 smoke：MAT-MR-2026-00006 -> PUR-ORD-2026-00025 -> MAT-PRE-2026-00007，PR 行保留 purchase_order/purchase_order_item/project
PR -> PI 本地 smoke：MAT-PRE-2026-00007 -> ACC-PINV-2026-00013，PI 行保留 purchase_receipt/pr_detail/purchase_order/po_detail/project
到货差异记录 smoke：MAT-PRE-2026-00007 上创建评论和 ToDo，并返回 1 行退货预览；不创建退货、不改变库存
```

本次 runner apply 创建的草稿单据：

| 单据类型 | 单据编号 | 说明 |
|---|---|---|
| Material Request | MAT-MR-2026-00004 | 城东项目劳保用品材料申请草稿 |
| Purchase Order | PUR-ORD-2026-00023 | 安科劳保用品采购订单草稿 |
| Purchase Receipt | MAT-PRE-2026-00006 | 安科劳保用品采购收货草稿 |
| Stock Entry | MAT-STE-2026-00005 | 城东项目帆布手套领料出库草稿 |
| Material Request | MAT-MR-2026-00005 | MR -> PO wrapper smoke 中创建并提交的材料申请 |
| Purchase Order | PUR-ORD-2026-00024 | 从 MAT-MR-2026-00005 生成的采购订单草稿 |
| Material Request | MAT-MR-2026-00006 | PO -> PR wrapper smoke 中创建并提交的材料申请 |
| Purchase Order | PUR-ORD-2026-00025 | PO -> PR wrapper smoke 中创建并提交的采购订单 |
| Purchase Receipt | MAT-PRE-2026-00007 | 从 PUR-ORD-2026-00025 生成并提交的采购收货；已用于 PR -> PI 和到货差异记录 smoke |
| Purchase Invoice | ACC-PINV-2026-00013 | 从 MAT-PRE-2026-00007 生成的采购发票草稿 |

## 下一步队列

1. 扩展一日运转 scenario runner，覆盖材料申请、采购、收货退货、项目领料、财务草稿和管理摘要的完整链路。
2. 给 runner 增加 apply 模式下的状态传递和引用关系验收，例如 MR -> submit MR -> PO -> submit PO -> PR -> submit PR -> verify stock impact -> QI/discrepancy -> PI -> project issue -> verify cost impact。
3. 继续补待采购工作台、逾期采购跟进、管理层日报等业务 wrapper。
4. 完成 `project-structure-cleanup-v0.3` 的全量验证并并入主分支。
5. 做自然语言 Agent Runtime，让“用户说人话 -> ToolCall -> ToolResult -> 人话回复”完整跑起来。
6. 增加企业监管层前的审计日志、确认策略和可观测性。
