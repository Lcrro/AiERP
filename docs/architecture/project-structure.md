# 项目结构与解耦边界

本文记录当前项目的长期目录边界。旧业务模拟的页面、seed/runner 和运行报告已经移除，不再作为项目结构的一部分。

## 核心分层

```text
员工工作台
  -> DeepSeek Agent Runtime
  -> Tool Contract / Resolver / ToolGateway
  -> ERPNext Adapter / agent_bridge
  -> ERPNext 开发账套
```

各层职责必须单一：

- Runtime 理解目标、规划动作和组织多轮对话。
- Tool Contract 定义参数、来源、校验、确认和修复方式。
- Resolver 只从真实主数据中解析 ERPNext 主键。
- ToolGateway 校验工具可见性、员工身份和确认状态。
- Adapter 只负责把合法 ToolCall 映射为 ERPNext/Frappe 调用。
- ERPNext 负责最终权限、业务校验、单据状态和持久化。

## 当前目录

```text
src/nexterp_agent/
  agent_runtime/       DeepSeek 规划循环、会话、Resolver、工具门禁
  erpnext/             Tool schema、Adapter、Client、模块 handler
  item_master/         物料规则、发布表检索、PostgreSQL 目录

frappe_apps/
  agent_bridge/        ERPNext 内复杂业务方法的受控入口

scripts/
  dev/                 本地服务、工作台和同步脚本
  erpnext/             主数据导入、账号初始化和 ERPNext 运维
  material_master/     物料治理、发布、检索和价格处理

data/
  master_data/         公司、组织、员工、项目、仓库、供应商等权威主数据
  material_master/     物料治理过程和发布版本
  runtime/             本地会话与运行报告，不作为权威主数据

docs/
  architecture/        架构和边界
  planning/            里程碑与开发计划
  reference/           ToolCall、主数据和 ERPNext 稳定事实
  operations/          本地运行、导入、验证和排障

tools/                 本地工作台和只读数据浏览页
tests/                 单元测试与 ERPNext 集成测试
```

## 依赖方向

允许：

```text
agent_runtime -> item_master
agent_runtime -> erpnext
erpnext adapter -> erpnext client
scripts -> src/nexterp_agent
tools -> 本地开发服务 API
```

禁止：

```text
erpnext -> agent_runtime
item_master -> agent_runtime
client -> adapter
权威主数据 -> runtime 会话
生产逻辑 -> 本地工作台页面
```

## 数据边界

- `data/master_data/` 和物料发布表是可重复导入的权威来源。
- `data/runtime/` 只保存本地状态，可以清空后重新生成。
- ERPNext 开发账套用于集成测试，不反向成为主数据唯一来源。
- 物料治理中间文件不得与最终发布表混用。
- 密钥、员工 API 凭据和真实生产业务数据不提交 Git。

## 测试边界

- `tests/unit/agent_runtime/` 验证规划动作、契约、Resolver 和确认流程。
- `tests/unit/erpnext/` 验证 Tool schema、Adapter 分发和标准错误。
- `tests/unit/item_master/` 验证物料检索、治理和发布数据。
- `tests/integration/` 才允许访问本地 ERPNext 开发账套。
- 集成测试创建的业务单据必须有稳定标记，并提供可重复清理方式。

## 新增功能规则

1. 先确定功能属于 Runtime、Tool 层、主数据层还是 ERPNext bridge。
2. 新 ToolCall 必须同时有 schema、contract、handler 和测试。
3. Link 字段必须通过 Resolver 或 ERPNext 真实返回值获得。
4. 写操作必须进入确认流程，并使用员工本人凭据执行。
5. 生成报告和临时会话写入 `data/runtime/`，不能混入权威发布目录。
