# Nexterp 无 AI 物资业务门户 v0.1

本版本把 `/` 作为员工物资门户，AI/聊天工作台保留在 `/developer/agent-workbench`。业务门户不调用 DeepSeek、OpenClaw，也不接受浏览器提交的员工身份、ERPNext 凭据或底层 ToolCall 参数。

## 沙盘初始化

目标账套固定为 `material-test.localhost`（本机端口 8003）。原始账套和凭据只放在被忽略的 `.runtime/erpnext-material-test/`、`.secrets/erpnext-material-test/`。

```powershell
.\scripts\test_env\material_test_site.ps1 bootstrap
python scripts\erpnext\sync_gpc_materials_to_test_site.py initialize
python scripts\erpnext\sync_gpc_materials_to_test_site.py plan
# 根据 plan 输出的 release_hash 生成 request_id 后再 apply
python scripts\erpnext\sync_gpc_materials_to_test_site.py apply `
  --request-id <uuid> --confirm-release-hash <release_hash>
python scripts\erpnext\bootstrap_material_test_business.py plan
# 根据 plan 输出的 plan_hash 后再 apply
python scripts\erpnext\bootstrap_material_test_business.py apply `
  --request-id <uuid> --confirm-plan-hash <plan_hash>
python scripts\erpnext\bootstrap_material_test_credentials.py
```

初始化脚本只创建缺失的公司、项目成本中心、项目仓、项目、测试供应商、采购价目表、五个沙盘用户和材料申请工作流。发现同名文档字段冲突时停止，不覆盖；重复 `request_id` 返回原结果。沙盘基线不创建交易或期初库存。

## 启动门户

在 `.env` 中配置 `NEXTERP_MATERIAL_TEST_BASE_URL`、`NEXTERP_MATERIAL_TEST_HOST_HEADER`、`NEXTERP_MATERIAL_TEST_CREDENTIALS_PATH` 和 `NEXTERP_MATERIAL_TEST_COMPANY` 后运行：

```powershell
python scripts\dev\material_business_portal.py
```

主页 `/` 是业务门户，物料商城 `/material-marketplace` 只展示本地发布且 ERPNext 已启用的物料；目录状态不可回读时禁止加入申请。所有写操作使用 `/api/business/commands/preview` → `/confirm` 两阶段接口，确认后通过 ERPNext 写入并立即回读。

## 首期接口

读取：`/api/business/bootstrap`、`/dashboard`、`/documents`、`/document`、`/inventory`、`/project-materials`。

写入：`/api/business/commands/preview`、`/api/business/commands/{command_id}/confirm`。当前白名单覆盖材料申请草稿、审批、询价、报价、采购订单、收货、差异和采购退货；正式单据状态仍以 ERPNext 为准。
