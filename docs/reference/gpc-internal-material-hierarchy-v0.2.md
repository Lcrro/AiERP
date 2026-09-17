# GPC 内部物料族与历史规格发布 v0.2

## 目标

GS1 GPC 2026-05 的四层官方目录保持只读且逐字不改。对宽口径 Brick，Nexterp 可增加带隐性来源属性的稀疏层级：

```text
GPC Brick → 内部物料族 → 内部标准类型 → 实际 SKU
```

内部物料族只负责聚合，实际物料只能挂在标准类型末级。v0.3 已取消直接挂 Brick 的兼容形态；内部来源和技术键只在数据库、API 与审计中保留，不在普通页面显性标记。

## 本次范围

- `10003185 螺栓/螺纹杆`：细分为螺栓、螺纹杆，再按六角、双头、高强度、结构专用、通用及全螺纹杆形成标准类型。
- `10003181 螺丝`、`10003179 锚栓/墙塞`：历史表中实际属于螺钉或膨胀锚栓的记录按 GPC 边界分流，不混入螺栓。
- `10008163 钢（成型）`：增加钢筋物料族，细分热轧带肋钢筋、抗震热轧带肋钢筋、精轧螺纹钢和盘螺。

## 数据规则

- 来源为本机工作簿“龙华项目物料待导入清单.xlsx”的“土木行业参考物料表”；工作簿只读，先由 artifact-tool 提取为本地 JSON，再由发布命令处理。
- 只发布能形成完整 SKU 身份的真实规格；螺栓至少需要可识别的直径和长度，钢筋至少需要牌号和公称直径。
- 历史别名按确定性规则标准化；相同标准类型、规格、材质/表面处理和等级的重复记录合并来源行。
- 参考表未写但可采用常用默认的字段必须在字段值中明确标注“常用默认”，不得伪装成源表事实。
- 只保留实际存在的组合，不生成属性笛卡尔积。

## 当前结果

- 输入命中行 233：螺栓相关 158、螺纹钢相关 75。
- 新增发布 180：紧固件 115、钢筋 65。
- 合并重复 12；不发布 41，其中包括规格不完整、牌号/直径不完整和明显错类记录。
- 连同既有首批物料，工作台共 259 项物料、82 个采购类型档案。
- SQLite 目录为 revision 5；官方 GPC 仍为 6463 个节点，内部扩展为 6 个物料族、17 个标准类型。
- ERPNext 写入为 0。

## 运行与核验

```powershell
python scripts/material_master/publish_historical_fastener_rebar_variants.py --input <artifact-tool-extract.json>
python scripts/material_master/sync_reference_catalog_database.py
python -m pytest tests/unit/item_master -q
python -m pytest tests/unit/agent_runtime/test_agent_workbench.py -q
python scripts/dev/project_context.py check
```

清洗审计报告保存在 `.runtime/material-master/historical-fastener-rebar-import-report.json`，运行期发布文件和 SQLite 不提交 Git。
