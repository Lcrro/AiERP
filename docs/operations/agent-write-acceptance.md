# Agent 写入能力验收

本文说明如何在本地 `civil` ERPNext 测试账套中重复验证真实 DeepSeek 写入链路。

## 覆盖范围

当前验收覆盖：

```text
项目经理自然语言 -> 项目任务草稿 -> 确认 -> ERPNext Task -> 回读
材料设备主管自然语言 -> 仓库调拨草稿 -> 确认 -> 提交 -> 库存台账核验
材料员自然语言 -> 项目领料草稿 -> 确认 -> 提交 -> 项目与库存台账核验
财务人员自然语言 -> 采购发票草稿 -> 确认 -> Purchase Invoice -> 回读
财务人员自然语言 -> 付款草稿 -> 确认 -> Payment Entry -> 回读
```

采购订单和采购收货由验收驱动器创建为最小来源夹具。Agent 产生的真实主键、来源关系和状态全部从 ERPNext 回读验证。

## 一键运行

确保本地 ERPNext `civil` 账套和 DeepSeek 配置可用，然后执行：

```powershell
python scripts\acceptance\agent_write_capabilities.py all
```

命令依次执行：

1. 校验胡银虎、潘丰、方文倩的 ERPNext 登录身份。
2. 校验项目、仓库、物料和供应商主数据。
3. 创建并提交最小采购订单和采购收货夹具。
4. 让真实 DeepSeek 准备项目任务，等待确认后执行并回读。
5. 临时建立正库存，让真实 DeepSeek 准备调拨和项目领料；明确提交后核验库存与项目台账。
6. 让真实 DeepSeek 准备采购发票，等待确认后执行并回读。
7. 提交测试发票作为付款来源。
8. 让真实 DeepSeek 准备付款草稿，等待确认后执行并回读。
9. 按本次 manifest 逆序清理单据和会话，并核对两仓库存恢复到整轮运行前。

最近一次完整结果写入：

```text
data/runtime/agent_write_capabilities_last_report.json
```

运行中的 manifest 写入：

```text
data/runtime/agent_write_capabilities_report.json
```

## 分步排查

```powershell
python scripts\acceptance\agent_write_capabilities.py prepare
python scripts\acceptance\agent_write_capabilities.py project
python scripts\acceptance\agent_write_capabilities.py stock
python scripts\acceptance\agent_write_capabilities.py finance
python scripts\acceptance\agent_write_capabilities.py verify
python scripts\acceptance\agent_write_capabilities.py cleanup
```

脚本只清理 manifest 中记录的本次单据，不扫描或删除其他业务数据。

真实 LLM 偶发可能在步数上限内未生成待确认动作。验收驱动器只在**尚未产生 ToolCall、尚未写入 ERPNext**时使用全新会话重试一次，并在结果中记录失败尝试。确认后的写操作绝不自动重试，继续由 `request_id` 和不可变确认摘要防止重复写入。

## 清理边界

ERPNext 已提交的采购、库存和财务单据可能生成审计或台账关系。日常验收清理会：

- 物理删除 Task、Payment Entry 草稿等未提交测试单据。
- 先取消已提交的 Purchase Invoice、Purchase Receipt 和 Purchase Order。
- ERPNext 不允许删除时保留 `docstatus=2` 的取消审计记录。
- 将保留项列入 `retained_cancelled`，但不视为活动业务单据。

需要让测试账套重新达到“业务单据总数为零”时，使用黄金基线恢复：

```powershell
.\scripts\test_env\reset_civil_sandbox.ps1 -Confirm RESET-CIVIL-SANDBOX
```

黄金恢复只允许作用于本机 `fac.localhost` 测试站点，并会清空工作台会话。
