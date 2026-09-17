# GPC 扩展层级统一编号 v0.4

## 规则

GS1 GPC 官方节点保持原 8 位编码不变。Nexterp 在官方节点下每增加一层业务分类，就在父编码末尾追加两位顺序号：

```text
官方 Brick 10008364
├─ 1000836401 排水泵用耐磨排水软管
└─ 1000836402 排水泵用透明钢丝增强吸水软管

官方 Brick 10003185
└─ 1000318501 螺栓
   ├─ 100031850101 六角螺栓
   ├─ 100031850102 双头螺栓
   └─ 100031850103 高强度螺栓
```

- 每个父级的直接子级使用 `01–99`。
- 已有合法数字编号保持稳定；新增兄弟节点使用最小未占用序号。
- 编号只表达父子关系和兄弟序号，不编码材质、规格或业务含义。
- `is_gpc=false`、`catalog_origin=nexterp` 和 `classification_source=nexterp_internal` 继续作为隐性来源属性，因此数字形式不会冒充官方 GPC 节点。

## 迁移结果

- 89 个自建目录节点全部从 `NXT-*` 迁移为 10/12 位层级编号。
- 83 个标准类型、6 个物料族、259 项实际物料和 81 个类型档案引用同步更新。
- 当前目录节点、实际物料、类型档案、发布规则和历史规格发布器中的活动 `NXT-*` 引用均为 0。
- SQLite 运行库推进到 revision 7；官方 GPC 节点仍为 6,463，ERPNext 写入 0。
- 写入前备份位于 `.runtime/material-master/publication-backups/normalize-20260814-100820/`。

迁移继续通过同一可重复运行命令执行：

```powershell
python scripts/material_master/normalize_gpc_material_workbench.py --dry-run
python scripts/material_master/normalize_gpc_material_workbench.py
```
