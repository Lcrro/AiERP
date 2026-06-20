# 当前 Codex 对话压缩上下文

生成日期：2026-06-20  
用途：给后续 Codex/开发者快速恢复项目上下文，避免重新从聊天记录里推断项目状态。

本文只记录工程事实、关键决策、当前状态和下一步建议。  
不记录 `.env`、API key、登录密码、个人访问令牌或其它敏感凭据。

## 项目愿景

目标是做一个基于 ERPNext 的企业级多员工 Agent 工作平台：

```text
企业员工
  -> 个人助理 Agent Runtime
  -> ToolCall
  -> ERPNext Adapter / 物料检索库
  -> ERPNext
```

最终体验不是“问 ERPNext”，而是员工和一个懂岗位、权限、待办、历史上下文、公司流程的个人助理协作。

核心定位：

```text
把 ERPNext 从“人找系统、填表、查菜单”
升级成“系统通过 agent 理解人、协助人、推动流程”。
```

## 当前架构判断

当前阶段重点不是接入完整自然语言 Agent Runtime，而是把底层可控链路做扎实：

```text
用户说人话
  -> 模型抽取结构化业务意图
  -> Runtime resolver 查询主数据/上下文
  -> 模型生成候选 ToolCall
  -> Runtime 校验和覆盖关键字段
  -> ToolGateway 做岗位工具门禁
  -> ERPNext Adapter 调 ERPNext/Frappe API
  -> ERPNext 后端权限和业务校验兜底
```

关键原则：

- LLM 负责理解人话和生成候选结构。
- Runtime 负责确定性上下文：日期、公司、项目、仓库、物料编码、权限边界。
- 模型不能凭空编造 ERPNext 主键。
- Adapter 是底层执行器，不应直接暴露给员工 Agent。
- 员工 Agent 必须通过 `ToolGateway`，由 profile 决定可见/可执行工具。
- ERPNext 后端权限仍是最终裁决层。

## 主要已完成内容

### 1. ERPNext ToolCall 工具层

已建立较完整的 ERPNext ToolCall 体系。

当前 ToolCall 合同规模：

```text
150 ToolCalls
agent_visible: 130
runtime_internal: 14
developer_only: 6
```

涉及模块：

- 通用文档操作
- Users & Permissions
- Assets
- Stock
- Buying
- Accounting
- Projects
- ToDo / Comment / Assign / File
- Workflow / Report

关键文件：

```text
src/nexterp_agent/erpnext/adapter.py
src/nexterp_agent/erpnext/modules/
src/nexterp_agent/erpnext/tool_schemas/
config/tool_contracts/
docs/reference/toolcall-data-dictionary.md
```

### 2. ToolCall Data Dictionary

已把 ToolCall 从散落文档整理成结构化契约。

关键文件：

```text
src/nexterp_agent/agent_runtime/tool_contracts.py
config/tool_contracts/*.yaml
scripts/docs/generate_toolcall_data_dictionary.py
docs/reference/toolcall-data-dictionary.md
```

字段包括：

- ToolCall 名称
- 用途
- 风险等级
- 是否暴露给 Agent
- 目标角色
- 确认级别
- 参数约束
- resolver
- repair 策略
- 后端 DocType / method 映射
- business contract

“待确认”项已按合理默认口径处理为：

- 默认口径
- 制度配置项
- 站点配置项
- 实现约定

### 3. Agent Runtime 门禁层

已新增：

```text
src/nexterp_agent/agent_runtime/tool_access.py
src/nexterp_agent/agent_runtime/tool_gateway.py
```

功能：

- profile 级工具过滤
- `agent_visible` / `runtime_internal` / `developer_only` 区分
- 运行前拒绝岗位不可用工具
- 可选 ERPNext 身份一致性校验

重要结论：

```text
ERPNextAdapter 仍能执行所有 handler；
员工 Agent 入口必须走 ToolGateway。
```

### 4. DeepSeek 材料申请试验

已接入 DeepSeek 做最小自然语言试验：

```text
自然语言材料需求
  -> DeepSeek 生成候选 Material Request ToolCall
  -> Runtime 校验/覆盖
  -> ToolGateway 执行
  -> ERPNext UI 可见草稿
```

关键文件：

```text
src/nexterp_agent/agent_runtime/deepseek_material_request.py
scripts/dev/deepseek_material_request_trial.py
data/scenario/deepseek_material_request_context.sample.json
docs/scenarios/deepseek-material-request-trial.md
docs/scenarios/deepseek-material-request-io-log.md
```

DeepSeek 当前只允许生成：

```text
erpnext.buying.create_material_request_draft
```

试验中发现并修正的问题：

- 第一次模型把“明天”算错。
- 第二次模型在已有 `default_schedule_date` 时仍追问今天日期。
- 后续加入规则：如果 Runtime 已提供 `default_schedule_date`，模型必须使用。
- 加入 `normalize_material_request_plan`，用 Runtime 上下文覆盖模型输出中的主数据和日期字段。

已实际创建 ERPNext 材料申请草稿：

```text
Material Request: MAT-MR-2026-00003
Item: SAFE-000005 帆布手套
Qty: 100 双
Project: PROJ-0001
Warehouse: SCEN-CIVIL 项目仓 - SD
Schedule Date: 2026-06-18
Status: Draft
```

### 5. Wizard of Oz 手动测试工作台

已建立手动 ToolCall 测试工作台，用于用户扮演 Agent，在接入完整大模型前人工点击/执行工具。

关键文件：

```text
src/nexterp_agent/scenarios/wizard_workbench.py
scripts/dev/wizard_workbench.py
scripts/wizard_workbench.py
tools/wizard_of_oz_workbench.html
docs/scenarios/wizard-of-oz-testing.md
```

用途：

- 展示沙盘 ToolCall
- 标记写入风险
- 触发本地 sandbox 执行
- 验证 ToolCall 是否足够支撑业务流

### 6. 小型土木公司一日业务沙盘

已建立小型土木公司沙盘数据和事件流。

角色包括：

- 总经理
- 财务主管
- 采购主管
- 行政采购员
- 仓库主管
- 项目仓管员
- 项目经理
- 施工班组长
- 供应商联络员
- 质检员
- 系统管理员

已准备的文档：

```text
docs/scenarios/civil-company-day-roles.md
docs/scenarios/civil-company-day-events.md
docs/scenarios/civil-company-day-seed.md
docs/scenarios/civil-company-day-readiness.md
docs/scenarios/civil-company-day-execution-log.md
docs/scenarios/civil-company-day-toolcall-coverage.md
```

本地 clean civil sandbox：

```text
http://localhost:8002
profile: civil
company: STEC (Demo)
```

注意：不要在文档中记录登录密码或真实凭据。

### 7. 物料主数据和检索方向

已经做过大量物料整理和治理工作，包括：

- 采购清单标准化
- SKU 草案
- 物料治理规则
- PostgreSQL 物料目录设计
- 物料浏览页
- 物料导入 ERPNext 的实验

当前架构结论：

```text
模型不能直接面对几千上万物料。
必须先由 Material Resolver 自动检索候选，再把 Top 3-10 个候选给模型。
```

推荐正式流程：

```text
用户自然语言
  -> LLM 抽取结构化业务意图草稿
  -> Runtime 拿 raw_item_text 查 Material Resolver
  -> Resolver 返回候选物料
  -> LLM 基于候选生成 ToolCall 或追问
  -> Runtime 校验/覆盖
```

Material Resolver 推荐检索策略：

- 规则归一化
- 精确编码匹配
- 标准名匹配
- 别名/土名匹配
- 模糊文本匹配
- 规格匹配
- 向量语义匹配
- 历史采购/项目常用物料加权
- 分数融合
- 业务重排
- 置信度决策

PostgreSQL 方向：

- `pg_trgm`：短词/错别字/近似名匹配
- Full Text Search：词项匹配和排序
- `pgvector`：语义向量匹配

## 当前 Git 状态

当前分支：

```text
codex/project-structure-cleanup-v0.3
```

当前远程：

```text
origin https://github.com/fillre/ERP-Agent.git
```

最近重要提交：

```text
9ec5f36 Add agent runtime governance and scenario tools
```

该分支已推送到：

```text
origin/codex/project-structure-cleanup-v0.3
```

## 最近测试状态

最近全量测试结果：

```text
165 passed, 3 skipped
```

常用测试命令：

```powershell
python -m pytest -q
python -m pytest tests\unit\agent_runtime -q
python -m pytest tests\unit\scenarios -q
```

## 当前关键设计结论

### LLM 和 Runtime 的边界

```text
LLM:
  - 理解自然语言
  - 抽取 intent draft
  - 生成候选 ToolCall
  - 在少量候选之间判断或追问

Runtime:
  - 日期解析
  - 主数据 resolver
  - ToolCall 参数校验
  - 上下文覆盖
  - 权限 profile
  - ToolGateway 执行
  - 审计记录
```

### DeepSeek 不应该直接知道物料编码

例如：

```text
帆布手套 -> SAFE-000005
```

不是模型知识，而是 Runtime 查询物料库后提供的上下文。

### 员工 Agent 不能直接用所有 ToolCall

应按 profile 暴露：

- 采购
- 仓库
- 项目经理
- 班组长
- 财务
- 资产管理员
- 系统管理员
- developer

底层通用工具如 `create_document`、`delete_document`、`call_method` 应保持 `developer_only` 或 `runtime_internal`。

## 下一步建议

优先级从高到低：

### 1. 做 Intent Draft 抽取

让 DeepSeek 先输出：

```json
{
  "intent": "create_material_request",
  "project_text": "城东项目",
  "warehouse_text": "项目仓",
  "schedule_text": "明天",
  "items": [
    {
      "raw_item_text": "帆布手套",
      "qty": 100,
      "uom": "双"
    }
  ]
}
```

不要一开始就生成最终 ToolCall。

### 2. 做 Material Resolver 自动上下文注入

输入：

```json
{
  "raw_item_text": "帆布手套",
  "qty": 100,
  "uom": "双",
  "project_text": "城东项目",
  "warehouse_text": "项目仓"
}
```

输出：

```json
{
  "status": "unique_match",
  "selected": {
    "item_code": "SAFE-000005",
    "item_name": "帆布手套",
    "stock_uom": "双"
  },
  "confidence": 0.96,
  "match_reasons": [
    "标准名称精确匹配",
    "单位匹配",
    "项目历史常用"
  ]
}
```

### 3. 把 DeepSeek 材料申请从 demo 脚本升级成 Runtime pipeline

当前：

```text
scripts/dev/deepseek_material_request_trial.py
```

后续建议：

```text
src/nexterp_agent/agent_runtime/pipelines/material_request.py
```

Pipeline 应包含：

```text
extract_intent
resolve_context
build_toolcall
normalize_toolcall
validate_toolcall
execute_or_return_confirmation
```

### 4. 把 Wizard of Oz 工作台接入 Runtime pipeline

让页面能选择：

```text
手动 ToolCall
DeepSeek dry-run
DeepSeek + Runtime resolver
DeepSeek + Runtime + execute
```

### 5. 继续推进一日业务流

从已创建的材料申请继续：

```text
Material Request
  -> submit
  -> Purchase Order
  -> Purchase Receipt
  -> discrepancy / return
  -> Purchase Invoice
  -> Project cost view
```

## 重要文件索引

入口文档：

```text
docs/README.md
docs/project-status.md
docs/project-thread-context-2026-06-20.md
```

架构：

```text
docs/architecture/roadmap.md
docs/architecture/project-structure.md
docs/architecture/toolcall-parameter-orchestration.md
```

ToolCall：

```text
docs/reference/toolcall-data-dictionary.md
docs/reference/toolcall-current-inventory.md
config/tool_contracts/
```

Agent Runtime：

```text
src/nexterp_agent/agent_runtime/tool_access.py
src/nexterp_agent/agent_runtime/tool_gateway.py
src/nexterp_agent/agent_runtime/tool_contracts.py
src/nexterp_agent/agent_runtime/deepseek_material_request.py
```

DeepSeek 试验：

```text
docs/scenarios/deepseek-material-request-trial.md
docs/scenarios/deepseek-material-request-io-log.md
scripts/dev/deepseek_material_request_trial.py
```

Wizard of Oz：

```text
docs/scenarios/wizard-of-oz-testing.md
tools/wizard_of_oz_workbench.html
scripts/dev/wizard_workbench.py
```

土木公司沙盘：

```text
docs/scenarios/civil-company-day-events.md
docs/scenarios/civil-company-day-readiness.md
docs/scenarios/civil-company-day-execution-log.md
scripts/scenarios/seed_civil_company_scenario.py
scripts/scenarios/run_civil_company_day_scenario.py
```

## 注意事项

- 不提交 `.env`。
- 不在文档中记录真实 API key、ERPNext API secret、登录密码。
- `ERPNextAdapter` 是底层执行器；员工入口必须走 `ToolGateway`。
- 远程 GitHub 仓库当前使用 `fillre/ERP-Agent`。
- 如果要推到 `milleryanla-ux/ERP-Agent`，需要该账号/仓库给当前 GitHub 凭据写权限。

