# GPC 物料层级与命名规范化 v0.3

## 目标

工作台继续以 GS1 GPC 2026-05 的官方四层目录作为只读参考骨架，但实际物料统一多一层“标准类型”：

```text
GPC Segment → Family → Class → Brick → 标准类型 → 实际物料
```

只有确有聚合价值的宽口径 Brick 才增加“物料族”；物料族是可选分组，不改变核心门禁：每个实际物料的直接分类父级必须是标准类型，不能直接挂在官方 Brick。

## 用户界面与溯源

- 页面按业务名称展示物料族、标准类型和实际物料，不显示“非 GPC”徽标或特殊颜色。
- 官方 GPC 编码仍按原样展示；内部节点从 v0.4 起使用“父编码追加两位”的业务层级编号，并在树、搜索、路径和详情中正常显示。
- `is_gpc=false`、`catalog_origin=nexterp` 和 `classification_source` 只作为数据库、API 与审计中的隐性来源属性。
- 官方 GPC 6,463 个节点和官方英文不修改，内部节点不得对外冒充 GS1 数据。

## 名称顺序

标准名称第一段固定为标准类型。紧固件采用：

```text
类型 → 规格 → 材质/表面处理 → 性能等级 → 结构/供货范围
```

例如：

```text
六角螺栓｜M14×160（全牙）｜镀锌｜8.8级｜单件
六角螺栓｜M20×50｜碳钢常规防锈（常用默认）｜4.8级（常用默认）｜按原表成套供货
```

历史别名“外六角螺栓”统一归并为“六角螺栓”。名称规范化只重排和规范已有字段，不生成属性笛卡尔积。

## 当前迁移结果

- 实际物料：259 项。
- 直接挂在官方 Brick 的物料：74 → 0。
- 标准类型：17 → 83，新增 66 个确定性标准类型。
- 类型档案：82 → 81；“外六角螺栓”档案并入“六角螺栓”。
- 统一重排标准名称：170 项。
- 259 项均写入隐性来源属性；旧 `NXT-*` 技术键已在 v0.4 全部迁移为数字层级编号。
- SQLite 运行库推进到 revision 6；ERPNext 写入 0。

## 运行与恢复

规范化命令可重复运行，默认只预览：

```powershell
python scripts/material_master/normalize_gpc_material_workbench.py
python scripts/material_master/normalize_gpc_material_workbench.py --write
```

写入前会备份运行期物料、类型档案和内部目录配置，并在临时文件上完成父级、属性模式和数据库同步校验后再替换正式文件。最近一次报告保存在：

```text
.runtime/material-master/gpc-workbench-normalization-report.json
```

该流程只更新内部参考目录与本地 SQLite，不触发 ERPNext。
