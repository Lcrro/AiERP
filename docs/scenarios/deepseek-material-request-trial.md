# DeepSeek 材料申请 ToolCall 试验

这个试验用于验证：

```text
采购/班组长说人话
  -> DeepSeek 生成候选 Material Request ToolCall
  -> ToolGateway 按岗位 profile 检查
  -> ERPNext Adapter 创建材料申请草稿
```

DeepSeek 只负责生成候选 JSON，不直接调用 ERPNext。真正执行仍必须经过 `ToolGateway` 和 ERPNext 后端权限。

## 配置

不要把真实 API key 发到聊天里，也不要提交到 Git。放在本机 `.env`：

```env
DEEPSEEK_API_KEY=你的 key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=60
```

DeepSeek 官方 API 当前支持 OpenAI 兼容格式，推荐使用 `deepseek-v4-flash` 或 `deepseek-v4-pro`。

## 只生成候选 ToolCall

```powershell
python scripts\dev\deepseek_material_request_trial.py --text "城东项目道路班组明天需要帆布手套100双，送到城东项目仓，用于劳保补充。"
```

没有 `--execute` 时不会写 ERPNext，只会输出：

```json
{
  "deepseek_plan": {
    "status": "needs_clarification",
    "questions": []
  }
}
```

或：

```json
{
  "deepseek_plan": {
    "status": "needs_confirmation",
    "tool_call": {
      "tool": "erpnext.buying.create_material_request_draft",
      "arguments": {}
    }
  }
}
```

## 带上下文

模型不能凭空编造 `item_code`、`warehouse`、`project`。实际使用时应先由本系统 resolver/search 工具查出候选，再作为上下文给模型。

```powershell
python scripts\dev\deepseek_material_request_trial.py `
  --context-json .\data\scenario\deepseek_material_request_context.sample.json `
  --text "城东项目道路班组明天需要帆布手套100双"
```

上下文示例：

```json
{
  "company": "STEC (Demo)",
  "current_date": "2026-06-17",
  "default_schedule_date": "2026-06-18",
  "project_candidates": [
    {"name": "PROJ-0001", "label": "城东道路改造项目"}
  ],
  "warehouse_candidates": [
    {"name": "SCEN-CIVIL 项目仓 - SD", "label": "项目仓"}
  ],
  "item_candidates": [
    {"item_code": "SAFE-000005", "item_name": "帆布手套", "stock_uom": "双"}
  ]
}
```

## 执行写入

确认 DeepSeek 生成的候选 ToolCall 正确后，再显式执行：

```powershell
python scripts\dev\deepseek_material_request_trial.py `
  --context-json .\data\scenario\deepseek_material_request_context.sample.json `
  --text "城东项目道路班组明天需要帆布手套100双" `
  --execute `
  --erpnext-profile civil `
  --agent-profile 采购员
```

执行结果会返回 `ToolResult`。如果岗位 profile 不允许、参数不完整、ERPNext 权限不足或服务端校验失败，写入会被拒绝并返回标准错误。
