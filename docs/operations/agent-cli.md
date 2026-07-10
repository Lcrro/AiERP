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

## 员工身份

首次使用前由测试账套初始化账号生成员工 API 凭据：

```powershell
python scripts\erpnext\bootstrap_employee_api_credentials.py --profile civil
```

凭据写入 `.secrets/erpnext-civil-users.json`，该目录被 Git 忽略。CLI 使用员工自己的 API key/secret，`ToolGateway` 会再次核对 ERPNext 当前登录身份。

## 当前能力

- DeepSeek 抽取材料申请业务意图。
- Runtime 解析公司、项目、仓库、日期、单位和物料。
- 模糊物料返回候选，不强行选择。
- 未找到物料进入新增物料提示。
- 写入前生成 ToolCall 预览。
- `--execute` 使用员工身份创建 Material Request 草稿。
- 关键状态和单据编号写入 `data/runtime/sessions/`，该目录不会提交。

当前 CLI 主线只开放材料申请。采购、收货退货、库存、财务和项目成本会继续沿用相同 Runtime 结构扩展。
