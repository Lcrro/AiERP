# DeepSeek 材料申请 ToolCall 试验

这个试验用于验证：

```text
采购/班组长说人话
  -> DeepSeek 生成候选 Material Request ToolCall
  -> ToolGateway 按岗位 profile 检查
  -> ERPNext Adapter 创建材料申请草稿
```

DeepSeek 只负责生成候选 JSON，不直接调用 ERPNext。真正执行仍必须经过 `ToolGateway` 和 ERPNext 后端权限。

## 推荐链路：模型抽意图，Runtime 填 ToolCall

现在推荐使用 `--use-runtime-resolver`：

```text
员工自然语言
  -> DeepSeek 只抽取业务意图草稿
  -> ReleaseMaterialResolver 查询发布版物料表
  -> material_request_orchestrator 检查公司、项目、仓库、日期、数量
  -> 高置信时生成 erpnext.buying.create_material_request_draft
  -> 不确定时返回候选给用户选
  -> 找不到时进入新增物料流程
```

这条链路的关键原则是：DeepSeek 不允许直接填写 `item_code`、`warehouse`、`project` 这类 ERPNext 主键。模型只负责抽出：

```json
{
  "intent": "create_material_request",
  "project_text": "城东项目",
  "warehouse_text": "城东项目仓",
  "schedule_text": "明天",
  "items": [
    {
      "raw_item_text": "帆布手套",
      "qty": 100,
      "uom": "双",
      "specs": {}
    }
  ]
}
```

后端 Runtime 再用发布版物料表和上下文生成真正 ToolCall。

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

## 使用 Runtime Resolver

```powershell
python scripts\dev\deepseek_material_request_trial.py `
  --use-runtime-resolver `
  --context-json .\data\scenario\deepseek_material_request_context.sample.json `
  --text "城东项目道路班组明天需要6.8级螺栓M12*40十个，送到城东项目仓。"
```

输出会分成两段：

```json
{
  "deepseek_intent": {},
  "runtime_plan": {
    "status": "ready | needs_material_selection | needs_item_creation | needs_clarification",
    "tool_call": {}
  }
}
```

典型状态：

- `ready`：物料、项目、仓库、日期、数量都已确定，可以生成 ToolCall 草稿。
- `needs_material_selection`：例如“帆布手套”有多个候选，需要用户选一个。
- `needs_item_creation`：发布版物料表没有找到可信候选，应进入新增物料流程。
- `needs_clarification`：缺项目、仓库、日期、数量等 ToolCall 必填信息。

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
