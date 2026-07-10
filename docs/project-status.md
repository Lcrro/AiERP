# 项目状态

最后更新：2026-07-10

## 当前版本

- 当前整理版本：`civil-agent-v1.0-foundation`
- 当前分支：`codex/project-structure-cleanup-v0.3`
- 整理基线：`996ae1e`
- 本轮状态：工程结构和 150 个 ToolCall 基线已经稳定；土木公司一日运转沙盘已通过人工 ToolCall 跑通主要采购、收货、退货、领料、财务和项目成本链。当前进入 v1.0 产品主线：统一物料与基础主数据发布版、构建干净 ERPNext 测试账套、完成自然语言 CLI Agent Runtime，并用员工身份重新执行完整一天事件流。

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
当前单元测试：176 passed
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

1. 固化价格就绪版 1,979 条物料和基础主数据为唯一发布源。
2. 实现干净 ERPNext 测试账套的 `plan/apply/verify` 幂等导入器。
3. 实现 DeepSeek 意图抽取、Resolver 注册表、参数编排、结构化会话和 CLI Runtime。
4. 用自然语言 Runtime 贯通材料申请、采购、收货退货、库存领料、财务和项目成本。
5. 按员工身份重新执行并记录 08:00 至 18:00 完整一天事件流。
6. 主线跑通后集中处理幂等、权限、审计、恢复和长尾数据问题。
