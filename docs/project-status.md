# 项目状态

最后更新：2026-06-09

## 当前版本

- 当前整理版本：`project-structure-cleanup-v0.3`
- 当前分支：`codex/project-structure-cleanup-v0.3`
- 整理基线：`996ae1e`
- 本轮目标：不新增业务 ToolCall，只整理当前可运行基线的工程结构。

## 当前结构

- Tool schema 已拆到 `src/nexterp_agent/erpnext/tool_schemas/`。
- 风险推断已拆到 `src/nexterp_agent/erpnext/risk_policy.py`。
- `ERPNextAdapter` 已拆成薄主类加模块 mixin：
  - `modules/generic.py`
  - `modules/users.py`
  - `modules/assets.py`
  - `modules/stock.py`
  - `modules/buying.py`
  - `modules/accounting.py`
  - `modules/common.py`
- 测试目录已整理为：
  - `tests/unit/erpnext/`
  - `tests/unit/item_master/`
  - `tests/integration/`

## ToolCall 覆盖状态

当前注册状态：

```text
137 tool schemas
137 adapter handlers
missing = []
extra = []
```

五个重点模块：

| 模块 | Tool 前缀 | Tool 数量 |
| --- | --- | ---: |
| 用户与权限 | `erpnext.users.*` | 18 |
| 资产 | `erpnext.assets.*` | 13 |
| 库存 | `erpnext.stock.*` | 35 |
| 采购 | `erpnext.buying.*` | 17 |
| 财务 | `erpnext.accounting.*` | 24 |

## 测试入口

常用命令：

```powershell
python -m pytest tests\unit\erpnext -q
python -m pytest tests\unit\item_master -q
python -m pytest tests\integration -q
python -m pytest -q
```

本地 ERPNext sandbox 集成测试需要先加载 `.env` 中的 `NEXTERP_LOCAL_*` 凭据。

当前验证结果：

```text
注册表一致性：137 schemas / 137 handlers / missing=[] / extra=[]
无显式 .env 全量测试：97 passed, 3 skipped
加载本地 sandbox .env 全量测试：100 passed
```

## 下一步队列

1. 完成 `project-structure-cleanup-v0.3` 的全量验证并并入主分支。
2. 继续补齐五大模块里仍需 `agent_bridge` 承载的复杂业务方法。
3. 做自然语言 Agent Runtime，让“用户说人话 -> ToolCall -> ToolResult -> 人话回复”完整跑起来。
4. 增加企业监管层前的审计日志、确认策略和可观测性。
