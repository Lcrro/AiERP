# 员工 Agent 网页测试台

## 启动

先启动独立 ERPNext sandbox：

```powershell
.\scripts\dev\start_wsl_sandbox.ps1
```

再启动 Agent 测试台：

```powershell
python scripts\dev\agent_workbench.py --port 8788 --profile civil
```

浏览器打开：

```text
http://127.0.0.1:8788/
```

## 测试步骤

1. 左侧先选择项目，再选择该项目下的员工和岗位。每个员工使用自己的 ERPNext API 身份和岗位权限。
2. 输入自然语言，点击“预览 Agent 操作”。预览不会写 ERPNext。
3. 在右侧检查意图、Resolver、ToolCall 和 ToolResult。
4. 写操作出现黄色确认栏后，点击“确认执行”才会写入。
5. 创建成功后，点击单据链接进入 `http://localhost:8002` 查看真实 ERPNext 单据。

右侧“业务单据”按采购、库存、财务、项目协作分组，使用当前员工身份查询项目相关单据；没有权限的模块会直接显示权限提示。

只读查询会在预览阶段直接执行。写操作使用浏览器生成的 `request_id` 防止重复点击造成重复建单。API key 和 secret 只在 Python 后端读取，不传给网页。

## 推荐话术

```text
合流1.3标明天需要20个6.8级螺栓M12*40，送到合流1.3标仓库，创建材料申请草稿

合流1.3标仓库还有多少6.8级螺栓M12*40

查询所有待采购的材料申请

今天公司有哪些异常需要我关注
```
