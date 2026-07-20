# 分层测试策略

项目测试按成本和反馈速度分层。原则不是“每次都跑得最多”，而是让当前改动先通过最接近的测试，再在阶段边界扩大验证范围。

## 四个层级

| 层级 | 内容 | 何时运行 | 目标 |
| --- | --- | --- | --- |
| 即时 | 当前文件或相邻单元测试 | 每次小修改后 | 1–5 秒内发现局部错误 |
| 模块 | Agent Runtime、采购、库存等单一模块 | 一项功能完成后 | 10–30 秒验证模块契约 |
| 全量 | 全部单元测试及可用的集成测试 | 阶段完成、提交和合并前 | 验证跨模块回归 |
| 昂贵验收 | 真实 DeepSeek、ERPNext 写入和完整业务闭环 | 相关主链变化或发布候选 | 验证真实跨系统行为 |

## 统一命令

```powershell
# 日常快速回归：Capability、失败案例和工具契约
.\scripts\test.ps1 quick

# 只验证 Agent Runtime
.\scripts\test.ps1 agent

# 阶段完成后的全量回归
.\scripts\test.ps1 full

# 需要本地 ERPNext 凭据
.\scripts\test.ps1 integration

# 真实 DeepSeek 稳定性基准，会产生 API 成本
.\scripts\test.ps1 llm

# 真实 ERPNext 写入闭环，会创建并清理测试单据
.\scripts\test.ps1 write

# 真实 ERPNext 非法路径验收，只允许 Capability 在写入前拒绝
.\scripts\test.ps1 write-negative
```

也可以直接使用 pytest 标记：

```powershell
python -m pytest -m unit -q
python -m pytest -m integration -q
python -m pytest -m "integration and not erpnext_write" -q
python -m pytest -m erpnext_write -q
```

## 标记定义

- `unit`：不依赖外部服务的快速测试，由 `tests/unit/` 自动添加。
- `integration`：依赖本地 ERPNext 或外部运行环境，由 `tests/integration/` 自动添加。
- `llm`：调用真实语言模型 API 的评测或测试。
- `erpnext_write`：会在本地 ERPNext 创建、修改、提交或清理数据。
- `slow`：只适合阶段或发布验收的长测试。

真实 LLM 和完整写入闭环目前使用 `scripts/acceptance/` 驱动器，不放进普通 pytest 收集过程，避免日常命令意外产生费用或业务数据。

## 维护规则

1. 纯 Python 规则只在单元测试验证，不在真实 API 验收中重复穷举。
2. 一个历史错误保留一个最小回归案例，避免复制整段业务流程。
3. 集成测试只验证系统边界、权限、来源关系和回读，不重复测试内部函数。
4. 真实写入必须有 manifest、幂等键和清理流程；确认后的写操作不自动重试。
   异常路径验收还必须核对来源单据指纹和相关 DocType 数量不变。
5. 真实 LLM 失败先进入候选报告，确认根因后才晋升为固定回归案例。
6. 已退出生产路径的旧实现只保留少量兼容测试，不继续扩张完整测试矩阵。

当前规模在几十秒内仍属健康。需要关注的是日常反馈时间、外部 API 成本和清理风险，而不是单纯追求更少的测试数量。

当前本机参考耗时：`quick` 为数秒，完整 Agent 模块约 23 秒，全量约 25 秒。耗时会随机器和环境变化，只用于选择合适层级。
