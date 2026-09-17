# 物料准入闭环 v0.8：确认、发布与 ERPNext 回读

## 目标

v0.8 把 v0.7 的服务器草稿接成完整发布闭环：

```text
采购清单分析
  -> 生成服务器草稿
  -> 员工修订受限业务字段
  -> 服务端重新编译并冻结草稿
  -> 员工确认 frozen_hash
  -> 以员工本人身份创建标准类型/SKU
  -> 创建 ERPNext Item
  -> 独立回读并逐字段验证
  -> 验证通过后加入 Nexterp 运行期检索目录
```

分析、初次生成草稿和草稿修订均不写 ERPNext。只有确认接口是写入边界。

## 两种发布动作

### 现有标准类型新增 SKU

程序继续使用冻结的标准类型字典，确定性生成编码、SKU 名称、物料组、单位、规格和 `Item` 字段。员工可修订规格值和库存单位，但不能提交任意 `item_doc`，也不能让模型编造底层 ToolCall。

### 新标准类型及首个 SKU

只有高召回检索没有可信类型候选、程序复核结论为 `new_type` 时才生成此草稿。员工必须核对：

- 一级分类、物料族和标准名称；
- ERPNext 中已存在的物料组；
- 企业物料编码前缀；
- 至少一个参与 SKU 唯一性判断的规格属性；
- 库存单位。

服务端使用分类、物料族和标准名称生成稳定 `type_id`，再生成该类型的首个 SKU。新标准类型不是新的 ERPNext `Item Group`；v0.8 只允许引用已经存在且当前员工有权使用的物料组和 UOM。

## 冻结与确认

### 生成草稿

```text
POST /api/material-intake/drafts
```

输入 `analysis_id` 和员工账号，返回服务端编译的草稿。每条草稿包含 `draft_id`、`revision` 和 `frozen_hash`。

### 应用修改并刷新预览

```text
POST /api/material-intake/drafts/revise
```

只接受受限业务字段：

```text
stock_uom
normalized_attributes
top_group
material_family
standard_name
definition
includes
excludes
item_group
code_prefix
```

服务端重新生成类型编号、物料编码、SKU 名称、规格文本、描述和 `Item` 字段，增加 `revision` 并返回新的 `frozen_hash`。`item_doc`、`item_code`、员工身份和 ToolCall 不接受前端修改。

### 确认并发布

```text
POST /api/material-intake/drafts/confirm
```

请求必须包含：

```json
{
  "analysis_id": "...",
  "user": "employee@example.com",
  "conversation_id": "...",
  "request_id": "稳定 UUID",
  "draft_ids": ["item-draft-..."],
  "draft_hashes": [
    {"draft_id": "item-draft-...", "frozen_hash": "..."}
  ]
}
```

确认接口拒绝同时提交草稿修改。服务器持有的 `frozen_hash` 与页面确认值不一致时不执行写入。同一个 `request_id` 再次调用只返回第一次结果；相同 ID 对应不同草稿摘要时拒绝执行。

## ERPNext 写入与回读

发布逐条执行：

1. 核对 API 登录用户与确认员工一致。
2. 检查物料编码是否已经存在。
3. 检查 `Item Group` 与 `UOM` 已存在。
4. 通过 `ToolGateway` 和 `erpnext.stock.create_item` 以员工身份创建 Item。
5. 不使用创建响应作为最终事实，重新调用 ERPNext `get_document`。
6. 比对编码、名称、物料组、库存单位、启停状态和采购/库存/销售标记。

同编码 Item 已存在且回读字段一致时，结果为 `verified_existing`，不会重复创建；字段不一致时结果为 `item_code_conflict`。创建成功但回读失败或不一致时标为 `readback_mismatch`，明确返回 `write_succeeded: true`，不把该记录加入 Nexterp 运行期目录。

## 运行期目录

ERPNext 回读完全一致后，服务端把标准类型快照和 SKU 快照追加到：

```text
data/runtime/material-intake-publications-v0.8.jsonl
```

这是被 Git 忽略的本地业务运行数据，不属于仓库发布版。工作台启动时会把它与不可变的物料发布版合并，后续分析可以召回刚发布的标准类型和 SKU。ERPNext 仍是 Item 是否存在及字段状态的最终事实来源；运行期目录只服务于 Nexterp 分类和检索。

## 验收口径

- 草稿修订不写 ERPNext，且前端不能传入任意 `item_doc`。
- 确认请求缺少 `request_id` 或 `frozen_hash` 时拒绝执行。
- 同一确认请求重复执行只创建一次。
- 已有 SKU 不重复创建；同编码不同字段被拦截。
- 新规格进入已确认标准类型并生成新 SKU。
- 新类型生成稳定类型编号与首个 SKU，回读通过后可被后续检索召回。
- ERPNext 回读不一致时明确显示不一致字段，不宣称闭环完成。
