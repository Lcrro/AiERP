# 员工 Agent CLI

第一版 CLI 入口：

```powershell
python scripts\chat_once.py --user mao.xiaoquan@stec-up.local "合流1.3标明天需要100个6.8级螺栓M12*40，送到合流1.3标仓库"
```

默认只编排和预览 ToolCall，不写 ERPNext。明确确认后增加：

```powershell
python scripts\chat_once.py --user mao.xiaoquan@stec-up.local --execute "合流1.3标明天需要100个6.8级螺栓M12*40，送到合流1.3标仓库"
```

查看完整意图、解析结果、ToolCall 和 ToolResult：

```powershell
python scripts\chat_once.py --user mao.xiaoquan@stec-up.local --json "..."
```

网络重试或服务重放时使用固定请求 ID，避免重复建单：

```powershell
python scripts\chat_once.py --user mao.xiaoquan@stec-up.local --execute --request-id mr-20260711-001 "..."
```

同一员工再次使用相同 `request_id` 时，Runtime 返回第一次结果，不再次调用 DeepSeek 或 ERPNext。

## 员工身份

首次使用前由测试账套初始化账号生成员工 API 凭据：

```powershell
python scripts\erpnext\bootstrap_employee_api_credentials.py --profile civil
```

凭据写入 `.secrets/erpnext-civil-users.json`，该目录被 Git 忽略。CLI 使用员工自己的 API key/secret，`ToolGateway` 会再次核对 ERPNext 当前登录身份。

## 当前能力

- DeepSeek 抽取采购、库存、财务、项目和管理摘要业务意图。
- Runtime 解析公司、项目、仓库、日期、单位和物料。
- 模糊物料返回候选，不强行选择。
- 未找到物料进入新增物料提示。
- 写入前生成 ToolCall 预览。
- `--execute` 使用员工身份创建和推进 MR、RFQ、PO、PR、采购退货、PI 和项目领料。
- 关键状态和单据编号写入 `data/runtime/sessions/`，该目录不会提交。
- 每次执行核对 API key 对应的 ERPNext 登录用户，身份不一致时拒绝执行。
- 通用查询工具仅允许 Runtime 内部编排，不能由员工 Agent 直接猜工具名调用。

全天沙盘执行：

```powershell
python scripts\scenarios\run_civil_agent_day.py --execute --continue-on-error
```

运行结果写入 `data/runtime/civil_agent_day_report.json`，中文摘要写入 `docs/scenarios/civil-agent-day-runtime-report.md`。
