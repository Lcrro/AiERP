# 材料申请审批流程

## 流程

合流 1.3 标的材料申请使用 ERPNext 原生 Workflow：

```text
材料员提交申请
  -> 待材料设备主管审批
  -> 待项目经理审批
  -> 已批准（Material Request 正式提交，docstatus=1）
```

当前人员对应关系：

| 环节 | 岗位 | 人员 | ERPNext 用户 |
| --- | --- | --- | --- |
| 发起 | 材料员 | 毛晓泉 | `mao.xiaoquan@stec-up.local` |
| 二级审批 | 材料设备主管 | 潘丰 | `pan.feng@stec-up.local` |
| 最终审批 | 合流项目经理 | 胡银虎 | `hu.yinhu@stec-up.local` |

## 状态与动作

| 当前状态 | 可执行角色 | 动作 | 下一状态 |
| --- | --- | --- | --- |
| 草稿 | `STEC Material Clerk` | 提交申请 | 待材料设备主管审批 |
| 待材料设备主管审批 | `STEC Material Equipment Manager` | 批准 | 待项目经理审批 |
| 待材料设备主管审批 | `STEC Material Equipment Manager` | 驳回 | 草稿 |
| 待项目经理审批 | `STEC Project Manager` | 批准 | 已批准 |
| 待项目经理审批 | `STEC Project Manager` | 驳回 | 草稿 |

材料员可以提交自己创建的草稿，但两个审批环节禁止自审。非当前审批角色即使知道动作名称，也会被 ERPNext Workflow 拒绝。

## 通知

进入待审批状态后，ERPNext 创建原生 `Workflow Action`。拥有当前审批角色的人员会在 ERPNext 桌面看到开放的审批动作。测试账号使用本地邮箱，因此当前关闭邮件发送，避免不可达邮件服务器拖慢审批；正式邮箱配置完成后可以再启用邮件提醒。

## 安装与复现

人员、项目和角色来源于 `data/master_data/release_v0_1/`。Workflow 安装入口为：

```text
agent_bridge.api.setup_material_request_approval_workflow
```

它会幂等创建专用角色、胡银虎的用户与 Employee、合流项目成员关系及完整 Workflow。真实 API 密钥只保存在 `.secrets/erpnext-civil-users.json`，不得提交。

