# 开发上下文恢复快照（2026-08-09）

## 用途

这份文档用于在 Codex Remote 会话缺失、页面无法加载或对话被压缩时恢复开发上下文。继续开发前，应以 Git 工作区、测试结果和本文档为准，不依赖聊天记忆推测代码状态。

本文档不包含 `.env`、API 密钥、ERPNext 凭据或真实业务数据。

## 会话恢复结论

- 当前 Codex 任务 ID：`019fc645-13ea-7a30-86ba-7ee3d7eada81`。
- 当前可读取的服务端任务记录和本机 rollout 文件都没有包含手机端缺失的几轮问答。
- 本机 rollout 文件约 `979.2 MB`。超大任务文件可能加重页面加载和同步问题，但不能据此断定缺失记录的唯一原因。
- 缺失的聊天文字目前无法从本机任务文件或可见的其他 Codex 任务中还原。
- 缺失期间产生的代码修改仍完整存在于 Git 工作区，可以从文件差异和测试恢复可靠开发状态。

## Git 基线

```text
仓库：ERP-Agent2
分支：codex/item-master-workbench-v0.8
HEAD：aaa71e6
远端同名分支：aaa71e6
最近提交：chore: make restored ERPNext sandbox reproducible
```

当前业务改动尚未提交。不得执行会丢弃工作区的 reset、checkout 或 clean 操作。

## 当前未提交功能

### 物料批量高召回检索 v0.6

主要文件：

```text
src/nexterp_agent/item_master/high_recall.py
src/nexterp_agent/item_master/runtime_aliases.py
src/nexterp_agent/item_master/batch_intake.py
tests/unit/item_master/test_high_recall.py
docs/reference/material-high-recall-v0.6.md
```

已实现：

- 整批采购清单事实提取。
- 按行高召回检索标准类型和 SKU。
- 动态候选门槛、分数构成、规格命中与冲突说明。
- 候选过多时分组压缩，同时在服务端保留完整结果。
- DeepSeek 批量判定和程序复核。
- 用户确认后记录运行期别名，分析阶段不自动学习。
- 分析过程不写入 ERPNext。

相关接口：

```text
POST /api/material-intake/analyze
POST /api/material-intake/confirm-alias
```

### 第八步：物料录入草稿 v0.7

主要文件：

```text
src/nexterp_agent/item_master/intake_drafts.py
tests/unit/item_master/test_intake_drafts.py
docs/reference/material-intake-draft-step-v0.7.md
```

已实现：

- 将当前分析结论编译为服务端持有的物料录入草稿。
- 合并重复的新 SKU 决定，跳过已有 SKU。
- 生成草稿时不写 ERPNext。
- 用户明确确认后，按当前员工身份通过 ToolGateway 写入 ERPNext。
- 执行前检查物料编码是否已存在，执行后返回创建、跳过和失败明细。
- 页面增加第八步、草稿列表和“确认并一键录入”按钮。

相关接口：

```text
POST /api/material-intake/drafts
POST /api/material-intake/drafts/confirm
```

## 当前修改文件

已修改的受 Git 跟踪文件：

```text
docs/README.md
src/nexterp_agent/item_master/__init__.py
src/nexterp_agent/item_master/batch_intake.py
src/nexterp_agent/workbench/server.py
tools/material_intake_lab.html
tools/workbench/material-intake-lab.css
tools/workbench/material-intake-lab.js
```

新增但尚未纳入 Git 的业务文件：

```text
docs/reference/material-high-recall-v0.6.md
docs/reference/material-intake-draft-step-v0.7.md
src/nexterp_agent/item_master/high_recall.py
src/nexterp_agent/item_master/intake_drafts.py
src/nexterp_agent/item_master/runtime_aliases.py
tests/unit/item_master/test_high_recall.py
tests/unit/item_master/test_intake_drafts.py
```

以下文件是本地运行日志，不应提交：

```text
data/runtime/agent-workbench.stderr.log
data/runtime/agent-workbench.stdout.log
data/runtime/material-browser.err.log
data/runtime/material-browser.log
```

## 验证状态

2026-08-09 重新执行：

```powershell
python -m pytest tests/unit/item_master/test_high_recall.py tests/unit/item_master/test_intake_drafts.py -q
```

结果：`9 passed`。

此前同一工作区的已知验证结果：

- 相关测试组：`50 passed`。
- 全量测试：`515 passed, 5 failed`。
- 5 个失败当时均不属于本轮物料功能：3 个是本地 ERPNext `8002` 不可用导致的集成超时，2 个是旧项目编码 `PROJ-0010` 与当前 `PRJ-HL-13` 的断言不一致。

## 继续开发检查表

1. 先运行 `git status --short`，确认上述未提交文件仍在。
2. 运行两组物料单元测试，确认高召回与草稿编译基线。
3. 启动工作台后检查 `/material-intake-lab`，完成“分析 → 生成录入草稿 → 确认录入”的人工验收。
4. 真实写入测试前确认 ERPNext sandbox、当前员工凭据和目标账套均正确。
5. 未经用户明确要求，不提交运行日志、凭据或本地状态目录。
6. 新的稳定进展应同步更新本文档或项目状态文档，避免再次只存在于超长对话中。

## 尚无法恢复的内容

手机端缺失问答中如果只有讨论、决策或待办而没有形成代码和文档，目前无法从工作区反推出原文。若手机端任务以后恢复显示，应把这些决策补录到项目文档；在此之前，任何新开发都先核对现有代码和测试，不假设缺失对话提出了额外要求。
