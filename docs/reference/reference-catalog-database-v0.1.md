# 参考目录 SQLite 运行库 v0.1

## 定位

参考目录工作台使用本机 SQLite 保存可浏览目录和已整理物料，减少单项分类调整对 Python/JavaScript 代码的影响。数据库只服务内部整理，不保存库存、价格、审批或 ERPNext 单据状态。

运行库：

```text
.runtime/material-master/reference-catalog.sqlite3
```

它被 Git 忽略，可由固定来源重新生成：

```powershell
python scripts\material_master\sync_reference_catalog_database.py --version 2026-05
```

## 表和边界

| 表 | 内容 |
| --- | --- |
| `catalog_state` | 目录版本、schema、revision 和来源元数据 |
| `catalog_nodes` | GPC 四层节点及内部物料族/标准类型；自建层级在父编码后追加两位 |
| `catalog_profiles` | 定义、包含、排除范围及工作译文 |
| `catalog_attributes` | Brick/内部末级属性 |
| `catalog_attribute_values` | 属性允许值 |
| `material_placements` | 已整理实际物料的完整 JSON 记录 |
| `procurement_type_profiles` | 稀疏 SKU/项目配置类型档案 |
| `catalog_change_log` | 批量同步和物料发布记录 |

`is_gpc=1` 的节点保存官方编码和英文；内部节点按父编码逐层追加两位 `01–99`，并明确保存 `is_gpc=0`、`catalog_origin=nexterp` 和 `classification_source`。内部来源由属性而不是编号前缀判定。内部节点不计入官方节点数量，也不得对外冒充 GS1 数据。实际物料的直接分类父级统一为标准类型，物料族只作为可选聚合层。

页面与公开工作台接口均为只读，不接受 SQL 文本。受信任的本机维护可以直接对业务表执行参数化 SQL；所有业务表触发器会推进 `catalog_state.revision`，页面在 revision 变化后自动局部重载。涉及多表的数据调整必须放在一个事务中，并在提交后回读 `summary`、`children/search` 和 `profile`。

## 发布与恢复

批量物料发布先对候选 JSONL 做完整性、目录叶子、类型档案和稀疏身份校验，再替换兼容 JSONL，并调用 SQLite 事务替换 `material_placements` 与 `procurement_type_profiles`。以后新增内部末级可直接进入数据库维护流程；版本化 JSON 配置暂保留为重建种子，直到形成正式数据库迁移与审阅命令。

若数据库缺失或损坏，停止 8788 工作台，移动损坏文件留作审计，然后重新执行同步命令。同步命令不会写 ERPNext；完成后必须确认：

```text
official nodes = 6463
internal standard types = 83（当前基线）
actual materials = 259（当前基线）
materials directly under official Brick = 0
parent missing = 0
duplicate code = 0
orphan Brick = 0
```
