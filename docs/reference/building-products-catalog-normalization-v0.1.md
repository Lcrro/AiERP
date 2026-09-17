# 建筑产品目录与多规格选择规范化 v0.1

状态：已完成当前安全边界内的规范化；ERPNext 历史 Item Code 重编待独立迁移。

日期：2026-08-28

## 本轮目标

- [x] 对建筑产品 130 个 SKU 做批量差异预览。
- [x] 去除“常用默认”等推断来源对可选属性值的污染。
- [x] 统一“成套供货”同义值，同时保留明确包含螺母、平垫、弹垫的采购差异。
- [x] 将员工不可理解的“头型待识别螺栓”改为“通用螺栓”，不虚构具体头型。
- [x] 保证同一标准类型下不存在完全相同、无法唯一解析的规格组合。
- [x] 多规格卡片按采购决策顺序显示属性，而不是按选项数量排序。
- [x] 多单位类型不再沿用第一条 SKU 的单位；选定唯一 SKU 后才显示实际库存单位。
- [x] 单规格卡片不再重复显示同一组三项属性。
- [x] 浏览器申请清单在目录 revision 变化后按源物料 ID 重新回读，避免保留旧名称或旧属性。
- [x] 同步独立测试账套并回读 259 个 ERPNext Item。

## 数据结果

- 本地参考目录数据库 revision：`12`
- 全目录：259 个 SKU、82 个标准类型
- 建筑产品：130 个 SKU、21 张类型/物料卡
- 规范化紧固件属性值：196 处
- 因规范化重建名称：109 项
- 规范化后重复选择组合：0
- “头型待识别螺栓”：0；“通用螺栓”：11 个 SKU
- ERPNext 发布哈希：`3e57b1a9913a79cb4b7b779afe9f2a8ce1a3e5696072f2d19a817b383a24a7db`
- ERPNext 同步 request_id：`07a04e5c-7e33-4a8b-b8a6-2f9c50e58435`
- ERPNext 回读：259 不变、0 更新、0 冲突、0 多余、字段不一致 0

原始推断依据没有删除：`confidence`、`specification_basis`、`source_reference` 和 `source_rows` 继续保留。员工界面只隐藏不属于采购选择维度的推断来源文字。

## 既有交易单据保护

测试账套已有 E2E 验收单据，因此目录验收不再错误地要求交易单据总数为 0。同步验收现在分别报告交易单据数量；目录一致性只由发布计划和逐项字段回读决定。后续同步会记录同步前后交易单据数量并要求完全一致。

## 独立后续迁移

当前有 86 个 ERPNext Item Code 是早期层级生成的纯数字稳定码，虽然物料已挂到当前第六层标准类型，但编码前缀仍是旧层级。它们已被材料申请、采购、收货和库存流水引用。本轮没有伪装显示码，也没有静默重命名这些 Item。

后续应做独立的 `Item Code` 重编迁移：

- [ ] 生成旧码 → 当前标准类型码 + 三位 SKU 序号的完整预览。
- [ ] 检查目标码占用、交换循环和所有来源单据引用。
- [ ] 仅在 `material-test.localhost` 使用 Frappe Rename Doc 两阶段临时码迁移。
- [ ] 回读 259 个 Item、全部来源单据和 Stock Ledger。
- [ ] 确认交易数量及数量金额未变化后，更新稳定 code map。

该迁移会改动既有测试单据中的物料链接，必须作为单独的可回滚里程碑执行，不能混入普通目录名称更新。

## 验证

```powershell
node --check tools/workbench/material-marketplace.js
.venv\Scripts\python.exe -m pytest tests/unit/item_master/test_material_catalog_normalization.py tests/unit/item_master/test_reference_catalog.py tests/unit/item_master/test_erpnext_material_release.py tests/unit/agent_runtime/test_business_portal.py tests/unit/agent_runtime/test_material_marketplace_legacy_cart.py -q
.venv\Scripts\python.exe scripts/erpnext/sync_gpc_materials_to_test_site.py verify
```

结果：43 项聚焦测试通过；ERPNext 259 项逐条回读一致。
