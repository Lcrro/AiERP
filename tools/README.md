# 本地工具页

这里放本地开发和数据查看用的小工具页面。

当前工具：

| 文件 | 用途 |
|---|---|
| `material_catalog_viewer.html` | 查看物料目录、治理结果和 SKU 草案的本地静态页面。 |
| `material_master_browser.html` | 按 `类目 -> 物料族 -> 物料名称 -> SKU` 四级查看物料主数据，默认读取发布版 v0.3。 |
| `project_module_map.html` | 用圆形节点和连线查看 Runtime、ToolCall、ERPNext、物料主数据和工程治理之间的关系。 |
| `agent_workbench.html` | 用真实员工身份预览和执行自然语言 Agent；后端默认运行在 `http://127.0.0.1:8788/`。 |
| `material_item_lab.html` | 独立测试自然语言标准物料分类、查重、确认和 ERPNext Item 回读；入口为 `http://127.0.0.1:8788/material-item-lab`。 |
| `agent_runtime_explorer.html` | 查看 Agent 八层运行架构、真实会话步骤和体验诊断；通过 `http://127.0.0.1:8788/agent-runtime` 访问。 |

规则：

- 这里的页面默认是开发/查看工具，不是生产系统 UI。
- 如果某个工具需要后端服务，应在文档里说明启动命令和访问地址。
- 长期可复用的前端应用后续应单独建应用目录，不继续堆在 `tools/` 根下。
