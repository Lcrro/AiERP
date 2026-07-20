# OpenClaw 接入边界

## 当前决定

暂不把 OpenClaw 作为 ERP Agent 核心 Runtime。当前核心继续由本项目负责：

```text
DeepSeek 语义理解
-> 业务能力 Runtime
-> Resolver / ToolContract / ToolGateway
-> ERPNext
```

OpenClaw 稳定后可以作为可替换的员工助理外壳，但不能成为 ERPNext 业务事实或权限来源。

## 适合交给 OpenClaw 的能力

- 企业微信、钉钉、网页等对话渠道。
- 员工语言偏好和低风险长期偏好。
- 定时唤醒、主动提醒和消息投递。
- 非 ERP 文档、邮件和日程协作。
- 调用本项目的一项高层业务能力并展示结果。

## 必须留在本项目的能力

- ERPNext 员工身份和本人 API 凭据。
- ERPNext 权限、工作流和审计。
- 真实主键 Resolver。
- 业务能力图和合法下一步判断。
- ToolCall 参数编译、Schema 校验和来源关系。
- 写操作确认摘要、幂等和执行后回读。
- 150 多个底层 ToolCall。

## 建议接口

OpenClaw 只调用三个概念接口：

### 准备业务动作

```http
POST /api/agent/turn
```

输入员工身份由服务端登录会话绑定，业务输入只包含项目上下文、会话编号和员工原话。输出可能是追问、候选卡或待确认业务动作。

### 确认业务动作

```http
POST /api/agent/confirm
```

确认必须引用服务端保存的 `conversation_id`、`request_id` 和待确认摘要。OpenClaw 不得重新拼 ToolCall。

### 读取结果

通过同一会话读取单据卡和可审计步骤。OpenClaw 只展示业务摘要，不保存 ERPNext 状态副本。

## 禁止的接法

- 把全部 Tool schema 注入 OpenClaw。
- 让 OpenClaw 保存员工 ERPNext API Secret。
- 让 OpenClaw 自己判断当前审批节点。
- 让 OpenClaw 绕过工作台确认直接执行写操作。
- 把 OpenClaw 记忆中的库存、金额或单据状态当作最新事实。

## 试验门槛

只有满足以下条件后才开始接入试验：

1. 采购自然语言评测集稳定通过。
2. 所有采购写动作都有确认摘要和执行后回读。
3. 库存、财务和项目能力也采用独立能力包。
4. 正式登录能够把外层会话绑定到唯一 ERPNext 员工。
5. OpenClaw 接入失败时可以直接切回现有工作台，不影响 ERPNext 数据。
