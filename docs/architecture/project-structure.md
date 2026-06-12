# 项目结构与解耦边界

本文定义 `nexterp agent` 的长期目录结构和模块边界。目标不是把文件摆得好看，而是让 AI + ERP 工程可以长期生长：Agent 大脑、ERPNext 工具层、物料主数据、业务沙盘、脚本和文档互相协作，但不互相缠住。

## 核心原则

1. `Agent Runtime` 是大脑，负责意图、状态、编排和回复。
2. `ERPNext Adapter` 是执行器，负责把合法 ToolCall 转成 ERPNext/Frappe API 调用。
3. `Tool schema` 是契约，不放业务状态，也不放自然语言 prompt。
4. `Item Master` 是物料主数据能力，不直接承担采购、库存、财务流程。
5. `Scenario` 是业务验收沙盘，不应该变成生产逻辑。
6. `Data` 是过程资产，必须区分原始数据、中间结果、最终发布候选和运行报告。
7. `Scripts` 是入口和批处理工具，不能成为隐藏业务核心。

一句话：

```text
大脑管决策，工具层管执行，物料层管主数据，沙盘管验收，数据层管证据。
```

## 目标顶层结构

```text
nexterp agent 2/
  src/
    nexterp_agent/
      agent_runtime/
      erpnext/
      item_master/
      scenarios/
      shared/
  frappe_apps/
    agent_bridge/
  config/
  data/
    material_master/
    scenarios/
    runtime/
  scripts/
    dev/
    erpnext/
    material_master/
    scenarios/
  tools/
  tests/
    unit/
    integration/
    scenario/
  docs/
    architecture/
    planning/
    reference/
    operations/
    scenarios/
```

当前项目还没有完全迁移到这个结构；本文先作为目标边界。迁移必须分批做，每批迁移后跑测试，不能一次性大搬家。

## 当前整理状态

已完成第一轮低风险整理：

- 已新增 `agent_runtime/` 包入口，用来承接后续自然语言大脑。
- 已新增 `scenarios/` 包入口，用来承接后续可复用业务沙盘逻辑。
- 已将 `scripts/` 按职责分为 `dev/`、`erpnext/`、`material_master/`、`scenarios/`。
- `scripts/` 根目录保留同名兼容 wrapper，旧命令暂时仍可运行。
- 已新增 `data/README.md`、`data/material_master/purchase_2024/README.md`、`data/scenarios/civil_company_day/README.md`，先建立数据分区规则。
- 物料大数据和沙盘报告暂未搬迁，等待脚本路径统一迁移后再做第二轮数据迁移。

## 运行时代码边界

### `src/nexterp_agent/agent_runtime/`

用途：未来放自然语言 Agent Runtime。

负责：

- 意图路由
- 工具包选择
- 多步状态编排
- 会话状态
- 结构化记忆
- ToolCall 生成
- ToolResult 到自然语言回答

不负责：

- 直接调用 ERPNext HTTP API
- 直接读写 ERPNext 数据库
- 直接修改物料治理 CSV

推荐子结构：

```text
agent_runtime/
  router.py
  state.py
  planner.py
  tool_selector.py
  response_writer.py
  memory.py
```

### `src/nexterp_agent/erpnext/`

用途：ERPNext 工具执行层。

已经存在：

- `adapter.py`
- `client.py`
- `schemas.py`
- `risk_policy.py`
- `tool_registry.py`
- `tool_schemas/`
- `modules/`

负责：

- 定义 ToolCall/ToolResult 协议
- 注册工具 schema
- 推断工具风险等级
- 执行 ToolCall
- 调用 ERPNext/Frappe API
- 标准化错误

不负责：

- 自然语言理解
- 多轮对话记忆
- 业务人员画像
- 物料治理规则生成
- 沙盘事件编剧

依赖规则：

```text
agent_runtime -> erpnext 允许
erpnext -> agent_runtime 禁止
erpnext -> item_master 允许有限依赖：只允许物料解析/规则能力
erpnext -> scenarios 禁止
```

### `src/nexterp_agent/item_master/`

用途：物料主数据、编码、规则和检索。

已经存在：

- `rules.py`
- `coding.py`
- `search.py`
- `postgres_catalog.py`

负责：

- 物料规则加载
- 编码生成
- 物料意图规范化
- 物料候选检索
- PostgreSQL 物料目录访问

不负责：

- 创建采购申请
- 创建采购订单
- 提交库存单据
- 决定财务入账

### `src/nexterp_agent/scenarios/`

用途：未来放可复用业务沙盘 runner 的 Python 逻辑。

当前沙盘脚本还在 `scripts/` 下，后续可以逐步把可复用逻辑迁到这里，只保留命令入口在 `scripts/scenarios/`。

负责：

- 场景步骤定义
- 场景运行状态
- 沙盘验收断言
- 测试数据引用

不负责：

- 生产业务逻辑
- Agent Runtime 决策
- ERPNext 通用工具实现

## Frappe App 边界

### `frappe_apps/agent_bridge/`

用途：部署到 ERPNext/Frappe 内部的桥接 app。

负责：

- 暴露 ERPNext 侧更稳定的业务方法
- 封装必须在 Frappe 服务端执行的逻辑
- 调用 Frappe 内部权限、工作流、报表或业务 API

不负责：

- Agent 对话
- 工具路由
- 大模型调用
- 本地 CSV/TSV 物料治理

边界规则：

```text
Agent Runtime 不直接调用 agent_bridge。
Agent Runtime 只生成 ToolCall。
ERPNext Adapter 再决定是否通过 Frappe API 调 agent_bridge。
```

## 数据目录边界

当前 `data/material_purchase_2024/` 已经积累了原始采购清单、标准候选、治理输出、导入报告、批处理文件。下一步应迁移成更清晰的结构。

### 目标结构

```text
data/
  material_master/
    purchase_2024/
      raw/
      working/
      curated/
      exports/
      reports/
      batches/
  scenarios/
    civil_company_day/
      seed/
      runs/
      smoke/
  runtime/
    sessions/
    logs/
```

### 分类规则

| 目录 | 放什么 | 例子 |
|---|---|---|
| `raw/` | 原始输入，只读，不改 | 原始采购清单导出的轻量表 |
| `working/` | 中间处理结果，可重复生成 | 拆批输入、治理队列、冲突队列 |
| `curated/` | 人工或规则确认后的稳定候选 | 标准物料候选、SKU 草案 |
| `exports/` | 给外部系统或 ERPNext 导入用 | ERPNext Item 导入 TSV |
| `reports/` | 校验、统计、导入结果 | summary JSON、import report |
| `batches/` | 分批处理输入/输出 | 50 行一批的子代理处理结果 |

### 重要规则

- 原始数据不覆盖。
- 中间数据可重建。
- `curated/` 里的文件才代表可继续用于建档或检索。
- ERPNext 导入结果放 `reports/`，不要和标准物料本体混在一起。
- 沙盘运行报告不要放进物料目录。

## 脚本目录边界

当前 `scripts/` 是平铺的。目标是按职责分区：

```text
scripts/
  dev/
    start_wsl_sandbox.ps1
    sync_agent_bridge.ps1
    smoke_erpnext.py
  erpnext/
    setup_item_master.py
    clean_demo_data.py
    import_standard_item_master_draft_to_erpnext.py
    verify_standard_item_import.py
  material_master/
    process_purchase_list.py
    build_standard_material_input.py
    split_standard_material_input_batches.py
    merge_standard_material_candidate_batches.py
    govern_material_catalog.py
    resolve_material_conflicts.py
    build_standard_item_master_draft.py
    run_material_search_eval.py
  scenarios/
    seed_civil_company_scenario.py
    run_civil_company_day_scenario.py
    validate_scenario_tool_coverage.py
```

迁移脚本前必须先检查引用路径。脚本迁移原则：

- 先迁移无外部引用的脚本。
- 再迁移测试覆盖的脚本。
- 每迁移一批，跑相关测试。
- 为常用入口保留兼容 wrapper，避免老命令立刻失效。

## 文档目录边界

当前文档结构基本合理，继续遵守：

```text
docs/
  architecture/  系统结构、边界和路线
  planning/      分版本计划和验收清单
  reference/     稳定事实、ToolCall 清单、规则、schema
  operations/    本地运行和维护
  scenarios/     业务沙盘、角色、事件和验收
```

新增文档放置规则：

| 文档类型 | 放置目录 |
|---|---|
| 架构边界、模块依赖 | `docs/architecture/` |
| 下一版本开发计划 | `docs/planning/` |
| ToolCall 清单、物料规则、字段契约 | `docs/reference/` |
| 本地启动、数据库、导入、排障 | `docs/operations/` |
| 土木公司一日运转、角色、事件 | `docs/scenarios/` |

## 测试边界

当前测试目录已经较清楚，后续目标：

```text
tests/
  unit/
    erpnext/
    item_master/
    agent_runtime/
  integration/
    erpnext/
    material_master/
  scenario/
    civil_company_day/
```

规则：

- `unit/erpnext` 验证工具分发、参数、风险和返回结构。
- `unit/item_master` 验证物料规则、编码、检索和治理脚本。
- `unit/agent_runtime` 验证意图路由、状态机、工具选择。
- `integration/erpnext` 才允许打本地 ERPNext sandbox。
- `scenario/` 验证业务链路，而不是单个函数。

## 严格解耦的依赖方向

推荐依赖方向：

```text
agent_runtime
  -> erpnext
  -> item_master
  -> shared

scenarios
  -> agent_runtime
  -> erpnext
  -> item_master

scripts
  -> src modules

tests
  -> src modules
```

禁止方向：

```text
erpnext -> scenarios
erpnext -> agent_runtime
item_master -> erpnext adapter
frappe_apps -> local data files
src modules -> scripts
```

如果某段逻辑被 `scripts` 和 `tests` 同时需要，应迁入 `src/nexterp_agent/...`，脚本只保留命令行入口。

## 下一步迁移顺序

第一批：只建边界，不搬大数据。

1. 新增本结构文档。
2. 在文档索引中加入入口。
3. 新增 Agent Runtime 目标目录和最小占位说明。
4. 新增 `src/nexterp_agent/scenarios/` 目标目录和最小占位说明。

第二批：整理脚本。

1. 建立 `scripts/dev/`、`scripts/erpnext/`、`scripts/material_master/`、`scripts/scenarios/`。
2. 迁移脚本并保留兼容 wrapper。
3. 跑相关测试和 smoke。

第三批：整理数据。

1. 建立 `data/material_master/purchase_2024/` 结构。
2. 移动物料数据，并同步更新脚本路径。
3. 建立 `data/scenarios/civil_company_day/`。
4. 移动沙盘报告，并同步更新文档链接。

第四批：接 Agent Runtime。

1. 新增 `agent_runtime/router.py`。
2. 新增 `agent_runtime/state.py`。
3. 新增 `scripts/chat_once.py` 或 `scripts/dev/chat_once.py`。
4. 用 08:20 材料申请场景做第一条自然语言闭环。

## 当前结论

项目不是“乱到不可救”，而是进入了第二阶段常见状态：能力已经长出来，但衣柜标签还不够。现在最重要的不是继续堆 ToolCall，而是把边界固定下来：

```text
ToolCall 能力继续放 erpnext/
物料治理继续放 item_master/
自然语言大脑新开 agent_runtime/
业务验证新开 scenarios/
数据按 raw/working/curated/exports/reports 分类
脚本按 dev/erpnext/material_master/scenarios 分类
```

这样后面无论接 LangGraph、MCP Server，还是继续做土木公司沙盘，都不会互相挤在一个抽屉里。
