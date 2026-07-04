# 本地工具页

这里放本地开发和数据查看用的小工具页面。

当前工具：

| 文件 | 用途 |
|---|---|
| `material_catalog_viewer.html` | 查看物料目录、治理结果和 SKU 草案的本地静态页面。 |
| `material_master_browser.html` | 按 `类目 -> 物料族 -> 物料名称 -> SKU` 四级查看物料主数据，默认读取发布版 v0.3。 |
| `wizard_of_oz_workbench.html` | 手动选择和执行 ToolCall 的 Wizard of Oz 测试工作台。 |

规则：

- 这里的页面默认是开发/查看工具，不是生产系统 UI。
- 如果某个工具需要后端服务，应在文档里说明启动命令和访问地址。
- 长期可复用的前端应用后续应单独建应用目录，不继续堆在 `tools/` 根下。
