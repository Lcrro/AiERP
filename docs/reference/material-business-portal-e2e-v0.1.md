# 物资门户完整闭环验收 v0.1

本验收只连接本机 `material-test.localhost`（8003），不触碰其他账套。验收驱动器位于
`scripts/acceptance/material_business_portal_e2e.py`，所有写操作都经过业务接口的
`preview → confirm`，并使用带 `E2E验收` 标记的 `request_id` 做幂等回放。

## 命令

```powershell
python scripts/acceptance/material_business_portal_e2e.py prepare
python scripts/acceptance/material_business_portal_e2e.py run --run-id <run_id>
python scripts/acceptance/material_business_portal_e2e.py verify --run-id <run_id>
python scripts/acceptance/material_business_portal_e2e.py cleanup --run-id <run_id>
python scripts/acceptance/material_business_portal_e2e.py all
```

`all` 会创建新的验收 run 并跑完整链路；成功 run 不执行 cleanup，保留单据供页面审阅。
报告写入 `.runtime/acceptance/material-business-portal/`，其中含 run_id、每个单据号、
request_id、来源关系、审批历史、库存前后值、Stock Ledger 回读和负例结果。该目录不提交 Git。

## 验收链路

使用三种纯数字物料（端子 4 件、螺栓 4 套、膨胀管 20 只）依次验证：材料申请创建、
驳回重提、主管审批、项目经理审批、双供应商 RFQ、两份报价、比价、采购订单、部分收货、
差异记录、采购退货、剩余收货、库存回读、项目领料和项目退料。最终库存应为收货数量，
领退料前后净变化为零；每张写入单据都在报告中保存 ERPNext 回读结果。

验收还覆盖非法物料号、过期 preview 和重复 request_id。负例必须零写入，重复 confirm
只能返回第一次的单据号。

## 测试账套基础资料

`bootstrap_material_test_business.py` 的沙盘计划包含 2026 财年、公司、成本中心、项目、
项目仓、测试供应商、价格表、五类测试身份和三级材料申请工作流。由于 ERPNext User 的
角色是子表，已提供一次性幂等同步：

```powershell
python scripts/erpnext/ensure_material_test_roles.py
```

该命令只为已有沙盘用户补齐声明角色（仓管包含 `Purchase User`，用于创建采购收货），
使用 Site Admin 凭据但不会输出凭据。

## 清理边界

`cleanup` 只处理指定报告中记录的单据；已提交单据按 ERPNext 规则取消，不删除审计记录。
草稿单据保留并在报告中标为 `draft_retained`，避免绕过 ERPNext 审计与链接校验。
