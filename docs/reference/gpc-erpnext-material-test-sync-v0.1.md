# GPC 到 ERPNext 物料测试账套同步 v0.1

## 定位

ERPNext 只作为无头事务内核。完整 GPC、多层 Nexterp 标准类型、属性、别名和审阅状态继续以参考目录 SQLite 为准；ERPNext 只接收经营物料组、UOM 和已经完整确认的实际 SKU。

```text
.runtime/material-master/reference-catalog.sqlite3
  -> 冻结发布包、哈希与差异预览
  -> 明确确认 release_hash + request_id
  -> Frappe REST 创建/更新
  -> 独立 GET 逐字段回读
  -> ERPNext Item 作为库存与单据真值
```

不把 6,463 个官方 GPC 节点复制成 ERPNext `Item Group`。当前只建立一个 `Nexterp经营物料` 根组和 14 个有实际物料的 Segment 经营组；完整路径保存在 Item 的只读关联字段中。

## 独立 Site

- URL：`http://localhost:8003`
- Site：`material-test.localhost`
- Docker project：`nexterp-material-test`
- 镜像：`frappe/erpnext:v15.118.2`
- 应用：Frappe、ERPNext
- 测试公司：`Nexterp物料测试有限公司`

Docker 编排来自固定的官方 `frappe_docker` commit。容器卷、发布包、同步日志和物料编码映射均为本机运行数据；站点密码和空白备份保存在 `.secrets/erpnext-material-test/`，不得提交或复制到文档。

创建或启动：

```powershell
.\scripts\test_env\material_test_site.ps1 -Action bootstrap
.\scripts\test_env\material_test_site.ps1 -Action start
.\scripts\test_env\material_test_site.ps1 -Action status
.\scripts\test_env\material_test_site.ps1 -Action stop
```

零物料基线在初始化公司、根物料组、必要 UOM 和 8 个只读 Item 关联字段后生成：

```powershell
.\scripts\test_env\material_test_site.ps1 -Action baseline
```

`baseline -Force` 只允许替换固定 `.secrets/erpnext-material-test/blank-baseline`，脚本会先验证绝对路径仍位于凭据目录内。

## 发布包与编码

只有 `completeness_status=完整` 且挂在 Nexterp `internal_type` 的实际物料能够进入发布包。SKU 编码采用：

```text
标准类型编码 + 三位顺序号
```

首次分配后，`material_id -> item_code` 映射保存在 Git 忽略的运行目录；后续新增物料从该类型已用最大序号继续分配，不因排序变化重编号。每个实际规格组合创建一个普通 ERPNext Item，不自动生成属性笛卡尔积变体。

Item 保留：源物料 ID、标准类型编码、官方 GPC Brick（如适用）、分类来源、完整路径、目录 revision、采购属性 JSON 和源字段 SHA-256。灭火器箱等内部类型不伪造 GPC Brick，使用 `classification_source=nexterp_internal`。

## 同步

先初始化并生成只读差异：

```powershell
python scripts\erpnext\sync_gpc_materials_to_test_site.py initialize
python scripts\erpnext\sync_gpc_materials_to_test_site.py plan
```

`plan` 输出冻结 `release_hash`。写入必须显式提交该哈希和 UUID：

```powershell
$requestId = [guid]::NewGuid().ToString()
python scripts\erpnext\sync_gpc_materials_to_test_site.py apply `
  --request-id $requestId `
  --confirm-release-hash <plan 输出的完整哈希>
```

相同 request_id 与相同发布哈希重复调用直接返回首次核验结果；同一 request_id 绑定不同发布哈希时拒绝。编码已存在但源物料 ID 不一致时标记冲突，不覆盖。

完整只读验收：

```powershell
python scripts\erpnext\sync_gpc_materials_to_test_site.py verify
```

验收逐项 GET 全部 Item 字段，并确认没有源外 Item；同时检查 Material Request、Purchase Order、Purchase Receipt、Purchase Invoice、Stock Entry、Stock Ledger Entry、Sales Invoice、Payment Entry 和 GL Entry 数量均为 0。

## 首次验收结果

- 来源：GPC `2026-05`、SQLite revision `7`
- 发布哈希：`b2cc2b6a6d18408486e52a248b52d6db50a572dc7be93eca521feaaad6c9f4fe`
- 经营物料组：15（1 个根组 + 14 个在用 Segment）
- UOM：16
- 标准类型：81
- Item/SKU：259
- 创建后完整回读：259 unchanged
- 冲突、额外物料、字段不一致：0
- 业务交易：0

当前同步入口是受控 CLI。工作台按钮属于下一里程碑，只允许调用固定测试 Site 的 `plan/confirm/apply/verify` 流程，不接受浏览器提交任意 ERPNext URL、凭据、Item 文档或低层 ToolCall 参数。
