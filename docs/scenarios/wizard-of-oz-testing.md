# Wizard of Oz ToolCall 手动测试

这个工作台用于在接入真实 Agent Runtime 前，让人先扮演 Agent。

目标链路：

```text
员工说人话
-> 你手动选择/编辑 ToolCall
-> ERPNext Adapter 执行
-> ERPNext 返回 ToolResult
-> 你观察结果是否符合业务直觉
```

## 启动

```powershell
python scripts\wizard_workbench.py --profile civil --port 8787
```

打开：

```text
http://127.0.0.1:8787/
```

## 沙盘基座

页面左上角有两个基座按钮：

| 按钮 | 行为 |
|---|---|
| 基座检查 | 执行 seed 脚本 dry-run，不写 ERPNext |
| 写入/补齐基座 | 执行 seed 脚本 `--apply`，创建或补齐沙盘人员、项目、仓库、供应商和初始库存 |

对应脚本：

```powershell
python scripts\seed_civil_company_scenario.py --profile civil
python scripts\seed_civil_company_scenario.py --profile civil --apply
```

基座数据包括：

- 人员与账号：15 个沙盘员工账号，默认禁用，仅用于业务上下文。
- 组织与项目：`STEC (Demo)` 下的城东、南区、西站三个项目。
- 仓库：中心仓和项目仓。
- 物料与供应商：一批土木采购常用物料、劳保/管材/建材/电气供应商。

## 手动 ToolCall

页面左侧是预设业务按钮，覆盖：

- 连接检查
- 基座数据检查
- 库存检查
- 项目提料
- 采购
- 收货
- 项目领料
- 财务查看

页面中间可以编辑当前 ToolCall 的 `arguments`。页面右侧显示真实返回的 `ToolCall` 和 `ToolResult`。

默认不执行写入类 ToolCall。要创建采购申请、采购订单、采购收货或项目领料草稿，需要先勾选：

```text
允许写入 ToolCall
```

第一版只把这些动作创建成草稿，不自动提交单据。

## 验收方式

建议按这个顺序点：

1. 基座检查
2. 检查当前 ERPNext 用户
3. 查看沙盘员工账号
4. 查看三个项目
5. 查看中心仓和项目仓
6. 查看沙盘供应商
7. 搜索帆布手套物料
8. 查项目仓帆布手套库存
9. 创建城东项目材料申请草稿
10. 查询待处理材料申请
11. 创建劳保采购订单草稿
12. 创建采购收货草稿
13. 预览项目领料是否足够
14. 创建项目领料草稿
15. 查看应付账款报表

如果这条线跑不通，优先修 ToolCall 或业务封装，再接自然语言 Agent。
