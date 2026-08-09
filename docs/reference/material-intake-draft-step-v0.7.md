# 物料接入第八步：物料录入草稿

## 目的

物料接入实验室在完成采购清单分析后，增加一个明确的人工确认边界：

```text
1-7 步：读取、提取事实、召回候选、DeepSeek 判定、程序复核
        ↓
第 8 步：生成服务器保存的物料录入草稿
        ↓ 用户确认
ERPNext：以当前员工身份创建 Item
```

分析和生成草稿都不写 ERPNext。只有点击“确认并一键录入”后，才会执行创建物料。

## 草稿来源

草稿只能由服务端保存的 `analysis_id` 编译产生，前端不能自行提交一组 `item_doc` 绕过分析。

可生成草稿的结论是：

- `new_sku`：使用已经存在的标准物料类型，在该类型下生成新的 SKU。

以下结论不会自动生成录入草稿：

- `existing_sku`：已有 SKU，不重复建档。
- `new_type`：需要先确认或治理新的标准物料类型。
- `needs_input`：候选、规格或单位仍不明确。

确定性编译器负责生成：物料编码、物料名称、物料组、库存单位、必填规格、辅助规格和 ERPNext `Item` 字段。DeepSeek 不直接填写 ERPNext ToolCall。

## 接口

### 生成草稿

```text
POST /api/material-intake/drafts
```

请求：

```json
{
  "analysis_id": "分析接口返回的 ID",
  "user": "当前员工的 ERPNext 账号"
}
```

返回内容包含：

- `drafts`：待确认草稿。
- `skipped`：未生成草稿的原始行及原因。
- `processing_step`：第八步统计。
- `writes_erpnext: false`：明确表示没有写入。

### 确认并录入

```text
POST /api/material-intake/drafts/confirm
```

请求只提交 `analysis_id`、当前员工账号和服务器生成的 `draft_id`：

```json
{
  "analysis_id": "分析接口返回的 ID",
  "user": "当前员工的 ERPNext 账号",
  "draft_ids": ["item-draft-..."]
}
```

服务端会依次执行：

1. 读取服务器保存的原始草稿，不接受客户端改写的物料字段。
2. 使用当前员工凭据核对 ERPNext 登录身份。
3. 逐条确认物料编码是否已存在；查询失败时本条不写入。
4. 通过现有 `ERPNextAdapter` 调用 `erpnext.stock.create_item`。
5. 返回已创建、已跳过和失败的明细。

重复点击不会重复创建已存在的编码。分析结果和草稿目前保存在工作台服务进程内，服务重启后需要重新分析；这不是 ERPNext 数据缓存，也不会修改正式物料表。

## 页面验收

1. 在 `material-intake-lab` 粘贴清单并点击“开始智能分析”。
2. 分析完成后出现第八步“生成物料录入草稿”。
3. 点击“生成录入草稿”，检查编码、名称、物料组、单位、规格和来源行。
4. 确认账号无误后点击“确认并一键录入”。
5. 页面显示创建、跳过和失败结果；ERPNext 中由当前账号权限决定最终是否允许创建。

