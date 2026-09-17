# 龙华 V4 分类示范账套

状态：已建立并完成首轮导入（2026-09-02）

## 用途与边界

这是一个与现有 `material-test.localhost` 隔离的 ERPNext 沙盘站点，用来审阅并实际测试
《龙华项目公司标准物料示范清单_第四轮附件治理.xlsx》中的分类、物料族和规格变体。
首轮只导入主数据；业务主数据初始化后允许在本账套创建测试申请、审批和后续采购单据，
所有测试交易仍与原 GPC 账套隔离，不会改变原账套库存、采购或总账。

ERPNext 仍是站点内物料主数据的事实来源；工作簿是本次发布包的来源依据。每个物料都保留
`source_dataset + source_document + source_sheet + source_row + source_row_hash`，不能只靠行号关联。

## 站点

| 项目 | 值 |
| --- | --- |
| Site | `material-classification-v4.localhost` |
| 浏览器地址 | `http://material-classification-v4.localhost:8004` |
| 容器项目 | `nexterp-material-classification-v4` |
| 访问端口 | `8004` |
| 公司 | `Nexterp分类示范有限公司`（`NCV`） |

站点凭据只保存在本机 `.secrets/erpnext-material-classification-v4/site-secrets.json`，不得写入文档、日志或提交记录。

## 已导入内容

- 386 个物料族；
- 917 个启用的规格变体（ERPNext `Item`）；
- 410 个可浏览的分类/物料族节点；
- 32 个单位（`UOM`）；
- 11 个 V4 物料来源字段和规格 JSON 字段；
- 1,280 条标准化采购流水和 991 条原始名称映射仅作为来源包统计，未创建采购单、收货单或库存流水。

发布哈希：`f5038b301f9cc30beeaba161dbea92718e07621c25a43b8679be24badb91d101`

## 可重复操作

```powershell
# 只读计划：显示将新增、保持不变和冲突的数据
& .venv\Scripts\python.exe scripts\erpnext\import_classification_v4_workbook.py plan `
  --input "$env:USERPROFILE\Downloads\龙华项目公司标准物料示范清单_第四轮附件治理.xlsx"

# 写入前必须使用 plan 输出的 release_hash，并提供新的 UUID request_id
& .venv\Scripts\python.exe scripts\erpnext\import_classification_v4_workbook.py apply `
  --input "$env:USERPROFILE\Downloads\龙华项目公司标准物料示范清单_第四轮附件治理.xlsx" `
  --request-id (New-Guid).Guid `
  --confirm-release-hash f5038b301f9cc30beeaba161dbea92718e07621c25a43b8679be24badb91d101

# 全量回读校验
& .venv\Scripts\python.exe scripts\erpnext\import_classification_v4_workbook.py verify `
  --input "$env:USERPROFILE\Downloads\龙华项目公司标准物料示范清单_第四轮附件治理.xlsx"
```

`apply` 的请求日志位于 `.runtime/erpnext-material-classification-v4/`。同一 `request_id` 在已验证后只返回原结果，不会重复创建物料；不同发布哈希或来源行哈希冲突会停止导入，不覆盖目标数据。

站点启停：

```powershell
& scripts\test_env\material_classification_v4_site.ps1 -Action status
& scripts\test_env\material_classification_v4_site.ps1 -Action stop
& scripts\test_env\material_classification_v4_site.ps1 -Action start
```

初始化脚本只操作 `nexterp-material-classification-v4` Compose 项目及其专用卷，不触碰现有物料测试账套。

## 本轮验证

- plan：410 个分类、32 个单位、917 个物料，无冲突；
- apply：917 个物料创建成功；
- 写后回读：917/917 检查通过，缺失 0、字段不一致 0；
- verify：通过；
- 使用相同 `request_id` 再次 apply：返回原验证结果，无重复写入；
- 历史采购流水导入为 ERPNext 交易：0。

## 门户与分类工作台

业务门户和物料商城的“分类版本”选择器同时提供：

- `原分类（GPC）`：连接 `material-test.localhost` 的当前采购目录，可正常发起申请；
- `ChatGPT 分类（龙华 V4）`：切换到本页所述独立分类账套的 917 个 SKU，并在该账套内
  回读启用状态；可创建测试申请和业务单据，不会写入原 GPC 账套。

切换由服务端白名单完成：原分类绑定 `material-test.localhost`，ChatGPT V4 绑定
`material-classification-v4.localhost`。浏览器只发送分类版本，不能发送 Site、公司、凭据或
底层 ToolCall 参数；服务端将账套写入会话 Cookie，并在每次预览、确认和写后回读时保持一致。
页面顶部会显示当前账套，避免在两个测试环境之间误操作。

当前分类工作台地址为 `/tariff-taxonomy-browser?catalog=gpc`，可通过
`&classification_source=chatgpt_v4` 直接打开 ChatGPT 版本；原来的
`/material-master-browser` 仍保留用于兼容旧书签，但不再作为门户主入口。
门户概览的物料目录数量、商城链接和工作台链接会随选择器同步；切换版本不会混用申请清单，
也不会混用另一账套的申请清单。两个分类版本都只允许使用各自 ERPNext 中已启用、可采购的物料。

初始化 V4 业务主数据（幂等，可重复运行）：

```powershell
& .venv\Scripts\python.exe scripts\erpnext\bootstrap_classification_v4_business.py
```

该命令只操作 `material-classification-v4.localhost`，并在 `.secrets/erpnext-material-classification-v4/`
生成站点专用的测试用户 API 凭据。
