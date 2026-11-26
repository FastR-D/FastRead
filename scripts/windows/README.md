# Windows 本地服务脚本

这些入口统一调用根目录 `run.bat` 和 `go-web.ps1`，启动 Go API、后台 worker，并由 Go 服务直接提供构建后的 FastUI 前端。默认访问 http://127.0.0.1:3015/。

| 脚本 | 用途 |
| --- | --- |
| `check.bat` | 检查 Go、Node.js、pnpm 和 Poppler。 |
| `start.bat` / `dev.bat` | 构建并启动本地服务。 |
| `status.bat` | 查看进程状态和 `/api/health`。 |
| `stop.bat` | 停止本入口启动的进程，保留资料。 |

需要 PowerShell 7。首次使用在根目录执行 `run.bat --init-admin` 设置管理员，再执行 `run.bat --no-open`。更新后使用 `run.bat --restart --no-open`；复用已有构建可附加 `--no-build`。配置、数据位置和 Linux 对应入口见根目录 README。

Docker 部署仍使用根目录 Docker Compose 配置，与这套原生进程脚本分别管理。
