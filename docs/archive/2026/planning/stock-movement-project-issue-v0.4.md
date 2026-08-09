# 库存调拨与项目领料 v0.4

更新日期：`2026-07-17`

## 目标

贯通土木项目采购收货后的库存使用链路：

```text
基地/中心仓库存
-> 库存调拨预检
-> Material Transfer 草稿与提交
-> 项目仓库存
-> 项目领料预检
-> Material Issue 草稿与提交
-> 项目成本和库存台账核验
```

ERPNext 仍是库存数量、单据状态、权限和 Stock Ledger Entry 的唯一事实来源。Agent 负责理解目标、查询真实主数据、准备操作和说明结果。

## 已完成

- 新增 `erpnext.stock.get_transfer_context`：批量读取源仓、目标仓实时库存，计算调拨后数量和缺料。
- 新增 `erpnext.stock.create_transfer_draft`：只创建经过库存校验的 Material Transfer 草稿。
- 新增 `erpnext.stock.verify_transfer_impact`：核对源仓负数量与目标仓正数量的库存台账。
- 保留项目专项工具：领料预检、创建 Material Issue 草稿、核验项目成本影响。
- 调拨和领料提交统一使用 `erpnext.stock.submit_document`，必须提供明确确认信息。
- 采购岗位可办理基地到项目仓调拨；项目岗位可办理项目领料，但不能创建跨仓调拨。
- 工作台增加“库存作业”页，按当前项目分页读取 Stock Entry，并可在单据抽屉直接提交。
- 调拨和领料 Tool Contract 已加入 Resolver、缺料拦截、确认和修复策略。

## 真实验收

可重复脚本：

```powershell
python scripts/acceptance/stock_movement_closed_loop.py prepare
python scripts/acceptance/stock_movement_closed_loop.py all
```

`all` 在本地 ERPNext 测试账套执行：

1. 蕰川路基地仓测试入库 3 包。
2. 调拨 2 包到合流 1.3 标项目仓。
3. 项目领用 1 包。
4. 核对调拨两端库存台账和项目领料成本行。
5. 反向取消三张测试单据，将两个仓库恢复到原始库存。

2026-07-17 验收结果：全部通过；测试单号 `MAT-STE-2026-00006` 至 `MAT-STE-2026-00008` 已取消，源仓和目标仓均恢复为 `0`。

## 未完成

- 真实 DeepSeek API 自然语言验收受外部数据发送审批限制，当前仅完成本地工具发现、契约和 Adapter 回归。
- 工作台还需用浏览器做一次库存作业页、单据抽屉和窄屏视觉验收。
- 后续补盘点、库存异常和管理层库存摘要，不在本次范围内。
