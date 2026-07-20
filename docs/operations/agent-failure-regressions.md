# Agent 失败回归库

## 两层数据

经过确认、以后绝不能复发的案例保存在：

```text
tests/fixtures/agent_runtime_failure_cases.json
```

真实 DeepSeek 稳定性基准发现但尚未人工判断的失败保存在：

```text
data/runtime/capability_runtime_failure_candidates_report.json
```

候选报告属于本地运行产物，不进入 Git。不能直接把一次模型输出当作正确答案，必须先确认：

1. 预期业务行为是否正确。
2. 错误来自模型、Runtime、Resolver、Tool Contract 还是 ERPNext。
3. 修复应放在强类型契约、Capability、确定性编译器还是执行边界。
4. 新测试是否能在不访问 DeepSeek 和 ERPNext 的情况下稳定复现根因。

## 当前覆盖

- `finish` 缺少用户消息。
- Capability 发现数量越界。
- 非 ISO 日期。
- 负数付款金额。
- Capability 意图出现无关字段。
- 第二轮补数量时丢失第一轮物料身份。
- 库存查询绕过 Capability 调用底层工具。
- 重复发现没有业务进展。

## 运行

固定回归案例：

```powershell
python -m pytest tests/unit/agent_runtime/test_agent_failure_regressions.py -q
```

真实 DeepSeek 基准及候选导出：

```powershell
python scripts/acceptance/capability_runtime_stability.py --rounds 4
```

只有经过审查的最小案例才能加入正式 fixture。不要把完整聊天记录、凭据或真实业务数据提交到测试目录。
