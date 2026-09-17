# Linux 开发机交接与恢复

## 目标

Linux 电脑直接运行 Nexterp、Docker Compose 和两个独立 ERPNext 测试账套，不依赖 Windows、WSL 或 Docker Desktop。ERPNext 仍是权限、工作流、库存和正式单据的唯一事实来源。

固定测试账套：

| 用途 | Site | 端口 |
| --- | --- | ---: |
| GPC 物料与业务闭环 | `material-test.localhost` | 8003 |
| ChatGPT V4 分类验证 | `material-classification-v4.localhost` | 8004 |

## 前置条件

- Git；
- Python 3.12；
- Docker Engine；
- Docker Compose v2（`docker compose`）；
- 通过安全渠道取得 V4 源工作簿；
- 需要沿用外部 API 时，通过密码管理器或加密通道单独取得 `.env` 值。

不要复制或提交 Windows 电脑上的 `.env`、`.secrets`、Docker 卷、数据库转储或 `.runtime` 日志。

## 1. 克隆并诊断

```bash
git clone https://github.com/Lcrro/AiERP.git
cd AiERP
python3 scripts/dev/team_handoff_bootstrap.py doctor \
  --v4-workbook /secure-transfer/classification-v4-source.xlsx
```

`doctor` 只读取 Git、Python、Docker 和文件状态，不创建账套。

## 2. 初始化两个测试账套

下面的命令会创建本机 `.venv`、生成本地随机测试密码、启动固定 Docker Compose 项目，并导入 GPC 与 V4 数据。它不会连接其他 ERPNext Site。

```bash
python3 scripts/dev/team_handoff_bootstrap.py bootstrap \
  --v4-workbook /secure-transfer/classification-v4-source.xlsx \
  --confirm BOOTSTRAP-NEXTERP-TEST-SANDBOX
```

生成的凭据只保存在 `.secrets/`，Linux 下权限设置为 `0600`。测试数据和运行时文件继续位于被 Git 忽略的 `.runtime/`。

## 3. 启停与检查 Site

```bash
.venv/bin/python scripts/test_env/material_sites.py --site material-test --action status
.venv/bin/python scripts/test_env/material_sites.py --site material-test --action start
.venv/bin/python scripts/test_env/material_sites.py --site material-test --action stop

.venv/bin/python scripts/test_env/material_sites.py --site classification-v4 --action status
.venv/bin/python scripts/test_env/material_sites.py --site classification-v4 --action start
.venv/bin/python scripts/test_env/material_sites.py --site classification-v4 --action stop
```

首次创建只使用 `bootstrap`。`stop` 仅停止容器并保留卷，不删除数据。

## 4. 启动物资门户

```bash
.venv/bin/python scripts/dev/agent_workbench.py --port 8788 --profile material_test
```

浏览器打开 `http://127.0.0.1:8788/`。V4 分类入口继续通过 `classification_source=chatgpt_v4` 切换，服务端按配置连接对应测试账套。

## 5. 回读验证

```bash
.venv/bin/python scripts/dev/team_handoff_bootstrap.py verify \
  --v4-workbook /secure-transfer/classification-v4-source.xlsx

.venv/bin/python -m pytest -q \
  -m "not integration and not llm and not erpnext_write and not slow"

.venv/bin/python scripts/acceptance/material_business_portal_e2e.py all
.venv/bin/python scripts/dev/project_context.py check
```

验收目标：

- GPC 259/259 回读一致；
- ChatGPT V4 917/917 回读一致；
- 非集成回归通过；
- 材料申请、审批、询报价、采购、收退货、库存和项目领退料闭环通过；
- 重复 `request_id` 不产生重复单据；
- `.env`、`.secrets` 和运行时数据未进入 Git。

## 6. 需要保留既有交易单据时

默认推荐在 Linux 重新生成空白测试账套并重新导入主数据。如果必须保留 Windows 测试账套中的交易链，应使用 ERPNext 官方备份与恢复流程；不要复制 Docker Desktop 的内部卷目录。恢复后仍需执行完整回读与 Stock Ledger 核验。

## 平台约束

- 路径由 `pathlib` 生成，不在 Python 中硬编码盘符或反斜杠；
- Python 虚拟环境入口在 Linux 为 `.venv/bin/python`，Windows 为 `.venv/Scripts/python.exe`；
- GitHub `quality` 在 Ubuntu 上运行，`windows-compatibility` 保留 Windows 回归；
- `main` 仍要求 Pull Request 和 `quality` 通过；
- 文件名在 Linux 区分大小写，新增代码必须使用仓库中的真实大小写。
