# 新电脑 ERPNext 沙盒恢复说明

本项目的新电脑沙盒使用 WSL2 + Docker Desktop 运行 ERPNext v15，站点为
`fac.localhost`，网页端口为 `8002`。工作台仍运行在 Windows 的 `8788` 端口。

## 当前结构

- Frappe/ERPNext：Docker Compose 项目 `nexterp-civil`
- ERPNext：`http://localhost:8002`
- 工作台：`http://127.0.0.1:8788`
- 自定义应用：`agent_bridge`
- 数据库：MariaDB，由 Compose 命名卷保存
- 物料目录 PostgreSQL：独立的 `nexterp-agent-material-postgres`

恢复数据来自本地归档，不把 `.env`、`.secrets` 或数据库密码提交到 Git。

## 重建应用镜像

`frappe_apps/agent_bridge/Dockerfile` 将自定义应用安装到 ERPNext 镜像中。Dockerfile
所在目录就是构建上下文：

```powershell
docker build -t nexterp/erpnext-civil:v15.108.0 frappe_apps/agent_bridge
```

当前 WSL Compose 文件仍保存在 `/home/sgj/nexterp/erpnext-civil/compose.yml`。
启动时同时加载仓库内的覆盖文件：

```powershell
wsl.exe -d Ubuntu-24.04 -- bash -lc "cd /home/sgj/nexterp/erpnext-civil && docker compose -p nexterp-civil -f compose.yml -f /mnt/c/Users/SGJ/Documents/nexterp\\ agent\\ 2/deploy/erpnext-civil/compose.custom.yml up -d"
```

这样所有 Frappe/ERPNext 服务使用同一个包含 `agent_bridge` 的镜像，而站点数据
仍然留在 Docker 命名卷中。

## 验收命令

```powershell
wsl.exe -d Ubuntu-24.04 -- bash -lc "cd /home/sgj/nexterp/erpnext-civil && docker compose -p nexterp-civil ps"
wsl.exe -d Ubuntu-24.04 -- bash -lc "docker exec nexterp-civil-backend-1 bench --site fac.localhost list-apps"
wsl.exe -d Ubuntu-24.04 -- bash -lc "docker exec nexterp-civil-backend-1 bench --site fac.localhost execute agent_bridge.api.ping"
```

不要使用 `docker compose down -v`，否则会删除数据库和站点卷。
