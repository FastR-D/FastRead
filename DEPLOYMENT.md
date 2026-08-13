# FastRead 笨蛋部署说明

这份说明给不想碰命令行的人用。当前默认推荐 Windows 本地启动：双击 `run.bat` 启动后端和前端，不要求 Docker。

## 第一次启动

1. 确认已经准备好本地依赖：`backend\.venv` 和 `fastread-frontend\node_modules`。
2. 双击 `run.bat`。
3. 等待后端和前端窗口启动完成。
4. 浏览器自动打开后，访问地址是：

```text
http://127.0.0.1:3015/
```

第一次启动前如果缺少依赖，按 `README.md` 里的本地依赖步骤先安装：

- 后端：创建 `backend\.venv` 并安装 `backend\requirements.txt`
- 前端：进入 `fastread-frontend` 后执行 `corepack enable` 和 `pnpm install`

## 日常使用

启动：

```text
双击 run.bat
```

查看状态：

```text
run.bat --status
```

停止：

```text
run.bat --stop
```

如果只想启动但不自动打开浏览器：

```powershell
.\run.bat --no-open
```

## 可选：Docker 部署路径

Docker 只作为可选部署或高级演示路径，不再是默认启动方式。确实需要容器部署时再使用：

```powershell
docker compose up -d --build
```

Docker 模式的访问地址仍是：

```text
http://127.0.0.1:3015/
```

## 常见问题

如果提示找不到 `backend\.venv`，先按 README 创建后端虚拟环境并安装依赖。

如果提示找不到 `fastread-frontend\node_modules`，先进入前端目录执行 `corepack enable` 和 `pnpm install`。

如果提示端口被占用，默认前端端口是 `3015`，后端端口是 `8483`。可以打开 `.env`，修改 `VITE_FRONTEND_PORT` 或 `BACKEND_PORT`，再重新启动。

如果页面能打开但联网核实失败，优先检查：

- 设置页里是否配置了模型供应商和模型。
- `.env` 或 `backend/.env` 里是否配置了联网检索供应商，例如 Brave Search。
- 后端日志里是否出现抓取失败、搜索不可用、来源被拦截等信息。
- `run.bat --status` 的健康检查是否成功。

如果你正在使用 Docker 可选路径，才需要检查 Docker Desktop 是否启动、`docker compose ps` 是否正常。
