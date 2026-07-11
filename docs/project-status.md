# 项目状态

最后更新：2026-07-11

## 当前版本

- 当前整理版本：`civil-agent-v1.0-runtime`
- 当前分支：`codex/civil-agent-v1.0`
- 本轮状态：150 个 ToolCall、权威主数据、独立 ERPNext 账套和员工身份 Runtime 已贯通；自然语言已真实跑通材料申请、采购订单、采购收货、差异待办、采购退货、采购发票、项目领料、库存和项目成本。下一步执行并记录完整一天事件流，再集中加固。

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
当前全量测试：210 passed, 3 skipped
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

1. 根据全天报告继续补充更丰富的岗位话术和业务数据，不再扩张底层通用工具。
2. 增加可供员工实际试用的对话前端和登录入口。
3. 在生产部署前补充审批策略、监控、备份和凭据托管。

阶段 2 实际账套验收：

```text
master-data operations = 4,243
verified = 4,243
failed = 0
Item = 1,979
Item Price = 1,979
```

首条自然语言闭环验收：

```text
员工：mao.xiaoquan@stec-up.local
输入：合流1.3标明天需要100个6.8级螺栓M12*40，送到合流1.3标仓库
解析物料：SPARE-000071-68
解析项目：PROJ-0010
创建草稿：MAT-MR-2026-00004
ERPNext owner：mao.xiaoquan@stec-up.local
```

跨岗位采购闭环验收：

```text
材料申请：MAT-MR-2026-00005（毛晓泉创建并提交）
采购订单：PUR-ORD-2026-00003（潘丰创建并提交，测试采购价 0.60 元/个）
采购收货：MAT-PRE-2026-00003（潘丰创建并提交）
采购发票：ACC-PINV-2026-00002（张振光创建并提交，金额 12.00 元）
项目领料：MAT-STE-2026-00006（毛晓泉创建并提交，成本 3.00 元）
退货链路：MAT-PRE-2026-00002 -> MAT-PR-RET-2026-00002
管理摘要：3 个只读 ToolCall 均成功
项目成本：PROJ-0010 查询成功
```

全天自然语言 Runtime 验收：

```text
事件时间：08:00 -> 18:00
事件数：17
完成：17
失败：0
主要产物：MAT-MR-2026-00009/10/11、PUR-ORD-2026-00005、PUR-RFQ-2026-00002、
          MAT-PRE-2026-00005、MAT-PR-RET-2026-00004、MAT-STE-2026-00008、ACC-PINV-2026-00004
审计报告：docs/scenarios/civil-agent-day-runtime-report.md
```
