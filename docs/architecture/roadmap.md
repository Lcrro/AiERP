# 架构路线图

这个路线图按架构阶段描述项目。

每个阶段回答一个问题：

```text
到这个阶段，系统架构应该具备什么能力？
```

路线图应该始终优先描述架构。产品功能可以后续逐步生长，但每个阶段都必须让系统结构更清晰、更有能力。

## 阶段 1：自然语言 ERPNext 闭环

架构目标：

```text
用户说人话
  -> Agent 把意图翻译成 ToolCall
  -> 系统执行 ToolCall
  -> ERPNext 返回 ToolResult
  -> Agent 把结果翻译回人话
```

这是第一个完整可运行的架构闭环。

阶段 1 暂时不追求深度业务优化。它要证明一件事：用户可以和助理对话，助理可以生成结构化 ERPNext 动作，Adapter 可以执行这些动作，助理也可以把 ERPNext 的结果解释回给用户。

目标架构：

```text
用户
  -> Chat / CLI / 简单 API 入口
  -> Agent Runtime
  -> ToolCall
  -> ERPNext Adapter
  -> ERPNext / Frappe API
  -> ToolResult
  -> Agent Runtime
  -> 自然语言回答
```

核心组件：

- Chat 或 CLI 入口
- Agent Runtime
- Tool schema 注册表
- ToolCall schema
- ToolResult schema
- ERPNext Adapter
- ERPNext/Frappe HTTP 客户端
- 基础 `agent_bridge` Frappe app
- 基础执行日志

已经存在：

- `ToolCall` and `ToolResult` schemas
- ERPNext Adapter
- ERPNext/Frappe HTTP 客户端
- WSL 中的本地 ERPNext sandbox
- 已安装到本地 ERPNext 的 `agent_bridge` app
- auth、客户查询、bridge ping 的 smoke 测试

仍然缺少：

- 自然语言输入入口
- Agent Runtime
- LLM 工具选择
- 从用户意图到合法 `ToolCall` 的转换
- 从 `ToolResult` 到自然语言回答的转换
- 基础对话/会话状态

阶段 1 验收标准：

- 用户可以输入自然语言请求。
- Agent 选择一个合法的 ERPNext tool。
- Agent 生成结构化 `ToolCall`。
- Adapter 执行这个 `ToolCall`。
- ERPNext 返回真实数据或真实校验错误。
- 结果被表示为 `ToolResult`。
- Agent 用自然语言解释结果。
- 整个闭环可以通过一个命令或一个 endpoint 跑起来。

目标命令示例：

```powershell
python scripts/chat_once.py --profile local "帮我查一个客户"
```

目标响应示例：

```text
我查到一个客户：Grant Plastics Ltd.
```

重要规则：

```text
Agent Runtime 可以选择工具。
Agent Runtime 不能直接调用 ERPNext HTTP API。
只有 ERPNext Adapter 可以和 ERPNext/Frappe 通信。
```

## 阶段 2：员工上下文与岗位助理层

架构目标：

```text
员工账号
  -> 用户上下文
  -> 岗位感知的助理画像
  -> Agent Runtime
  -> ERPNext 工具
```

阶段 2 在阶段 1 闭环之上增加身份和岗位层。

系统应该知道员工是谁、属于什么岗位，以及应该用哪个助理画像来指导 agent 的行为。

目标架构新增内容：

- 员工/用户上下文模型
- ERPNext 用户映射
- 岗位到助理的注册表
- 助理画像
- 岗位专属 tool 提示
- 岗位专属 DocType 提示
- 岗位专属回答风格

岗位示例：

- 采购
- 销售
- 仓库
- 财务
- 技术员
- 项目经理
- 公司经理
- 普通员工

验收标准：

- 用户可以映射到一个 ERPNext 账号。
- 系统可以加载岗位感知的助理画像。
- 同一个 Agent Runtime 可以根据岗位上下文表现出不同工作方式。
- 阶段 1 的闭环在底层保持不变。

## 阶段 3：ERPNext 知识与 DocType 索引层

架构目标：

```text
ERPNext 元数据
  -> DocType index
  -> 字段/schema 摘要
  -> Agent 工具规划上下文
```

阶段 3 让 agent 理解 Nexterp/ERPNext 的结构，而不是只依赖 prompt 和硬编码示例。

目标架构新增内容：

- DocType 爬取/索引器
- DocType schema 缓存
- 字段摘要生成器
- 子表映射
- Link 字段映射
- 必填字段识别
- 可提交/工作流元数据
- 报表/method 注册表

验收标准：

- 系统可以列出可用 DocType。
- 系统可以总结某个 DocType 的重要字段。
- agent 在创建/更新文档前可以检查 schema。
- agent 可以针对缺失必填字段追问用户。
- 字段调试可以通过索引和实时 ERPNext 元数据完成。

## 阶段 4：业务流程编排层

架构目标：

```text
用户目标
  -> ActionPlan
  -> 多个 ToolCall
  -> 中间 ToolResult
  -> 最终业务回答
```

阶段 4 把单次工具调用升级成多步骤 ERP 工作流。

目标架构新增内容：

- ActionPlan schema
- 多步骤规划器
- 中间状态存储
- 追问处理
- 先草稿后执行的模式
- 工作流模板
- 可行范围内的回滚/纠错策略

验收标准：

- agent 可以在执行前规划多个 ERPNext 操作。
- agent 可以暂停并追问缺失信息。
- agent 可以在高影响操作前先创建草稿。
- 阶段 1 的 ToolCall 闭环仍然是执行单元。

## 阶段 5：主动 Agent 调度层

架构目标：

```text
定时监控
  -> Agent/Tool 执行
  -> 发现业务事件
  -> 员工通知或建议动作
```

阶段 5 让系统可以主动发起工作，而不只是回复用户消息。

目标架构新增内容：

- 定时任务
- 已保存的监控项
- 通知队列
- 员工每日简报
- 管理层异常摘要
- 建议动作队列

验收标准：

- 系统可以定时运行 ERPNext 检查。
- 系统可以生成岗位专属提醒。
- 提醒可以转化为用户确认后的 ToolCall。

## 阶段 6：监管 Agent 与策略层

架构目标：

```text
个人助理 ActionPlan / ToolCall
  -> 监管 Agent / 策略审查
  -> 允许 / 确认 / 拒绝 / 升级
  -> ERPNext Adapter 执行
```

阶段 6 把企业控制能力作为独立层加入系统。

目标架构新增内容：

- 策略引擎
- 监管 agent
- 风险分类
- 动作确认
- 审批升级
- 审计看板
- 不可变动作日志

验收标准：

- ToolCall 可审计。
- 高风险动作可以被拦截。
- 监管层独立于个人助理。
- 系统可以解释某个动作为什么被允许或拦截。

## 阶段 7：生产运行层

架构目标：

```text
可靠的多用户服务
  -> 安全凭据
  -> 日志和监控
  -> 重试和队列
  -> 本地与远程 Nexterp 支持
```

阶段 7 把系统加固到可以支撑真实公司使用。

目标架构新增内容：

- 密钥管理
- 每用户或委托式 ERPNext 身份
- 速率限制
- 结构化日志
- 重试和幂等
- 后台 worker 队列
- 部署脚本
- 监控
- staging/production 配置

验收标准：

- 本地和远程 Nexterp profile 都通过同一个 adapter 工作。
- 不提交任何密钥。
- 失败的工具调用可见且可恢复。
- 系统可以支持多个员工账号。

## 近期架构目标

完成阶段 1。

下一个代码目标是：

```text
scripts/chat_once.py
  -> 接收自然语言
  -> 调用 Agent Runtime
  -> 得到 ToolCall
  -> 执行 ERPNextAdapter
  -> 把 ToolResult 送回 Agent Runtime
  -> 打印自然语言回答
```
