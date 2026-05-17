# ReelMind 笨蛋部署说明

这份说明给不想碰命令行的人用。推荐 Windows + Docker Desktop。

## 第一次启动

1. 安装 Docker Desktop，并打开它。
2. 双击 `CHECK_REQUIREMENTS.bat`，确认 Docker、端口和磁盘空间没有明显问题。
3. 双击 `START_HERE.bat`。
4. 浏览器自动打开后，访问地址是：

```text
http://127.0.0.1:3015/
```

第一次启动会下载基础镜像、安装依赖、构建前端，可能需要几分钟。

如果没有安装 Docker Desktop，`CHECK_REQUIREMENTS.bat` 和 `START_HERE.bat` 会打开 Docker 下载页面。安装完成后要先打开 Docker Desktop，等它启动完成，再运行本项目。

## 日常使用

启动：

```text
双击 START_HERE.bat
```

查看状态：

```text
双击 STATUS_HERE.bat
```

停止：

```text
双击 STOP_HERE.bat
```

如果只是重启，不想重新构建镜像：

```powershell
.\START_HERE.bat --quick
```

## 常见问题

如果提示 Docker 不可用，先打开 Docker Desktop，等左下角或顶部状态显示运行中，再重新双击 `START_HERE.bat`。

如果提示端口被占用，默认端口是 `3015`。可以打开 `.env`，把 `APP_PORT=3015` 改成别的端口，例如 `3020`，再重新启动。

如果页面能打开但生成笔记失败，优先检查：

- 设置页里是否配置了模型供应商和模型。
- 抖音 Cookie 是否已经通过浏览器扩展同步。
- `STATUS_HERE.bat` 的健康检查是否成功。
