# FastRead 笨蛋部署说明

这份说明优先服务普通 Windows 用户：有正式 Release 时，默认使用安装包；`run.bat` 保留给源码开发和本地调试，不要求 Docker。

## Windows 安装包（推荐）

1. 在 [GitHub Releases](https://github.com/FastR-D/FastRead/releases) 下载同一版本的 `*-setup.exe` 和 `SHA256SUMS-x86_64-pc-windows-msvc.txt`。普通用户优先选择 NSIS `setup.exe`；MSI 用于管理员或受管环境部署。
2. 在下载目录核对 SHA-256：

```powershell
(Get-FileHash .\FastRead-setup.exe -Algorithm SHA256).Hash
```

3. 核对无误后运行安装程序。NSIS 默认安装到当前用户，不需要选择数据库目录；缺少 WebView2 Runtime 时安装程序会联网下载并静默安装。完全离线的机器应先由管理员部署 WebView2 Runtime。
4. 从开始菜单启动 FastRead。桌面程序会自动启动随附后端，不需要另开终端。

目前 CI 会生成校验和，但尚未配置 Windows/macOS 代码签名。未签名的 Windows 安装包可能触发 SmartScreen；这不应被当作正式公开发行的最终状态。接入签名证书后，还应配置可信时间戳并在干净 Windows 虚拟机上完成安装、升级、卸载和重启验收。

当前错误状态动画包含 Lottie 表达式，因此桌面 CSP 暂时保留了 `script-src 'unsafe-eval'` 兼容权限。它不是长期安全目标：后续应换成不含表达式的动画或不依赖运行时求值的渲染方案，完成错误路径验收后移除该权限。

### 升级、备份和卸载

- 直接运行更高版本安装包即可升级；Windows 安装配置会阻止降级，MSI 的升级标识在所有后续版本中必须保持不变。
- 后端数据默认位于 `%APPDATA%\com.fastread.app`，包括数据库、论文、上传文件、笔记、索引、配置和本地密钥材料。WebView 配置位于 `%LOCALAPPDATA%\com.fastread.app`，其中包含个人总结草稿、首次使用状态和浏览器缓存。两处都与安装目录分离。
- 备份前先退出 FastRead，再复制上述两个目录。受管部署可在启动前设置绝对路径 `FASTREAD_DATA_ROOT`，把后端数据改到指定目录；相对路径会被拒绝。
- 默认卸载只移除 FastRead 应用和随附后端，不删除上述用户数据。这样重装后仍能继续使用原数据库、论文、索引、设置和本地草稿。
- 如果要彻底清除，在卸载后手工删除上述两个目录。这个操作会永久删除数据库、论文、上传文件、笔记、索引、配置、本地草稿以及保存的密钥材料，删除前请确认备份。

安装包发布时至少应同时提供安装文件和对应目标的 `SHA256SUMS-*.txt`。版本号必须在 `tauri.conf.json`、`Cargo.toml` 和 Git tag 中一致；只有所有平台打包任务都成功且产物非空时才创建 Release。

## 从源码启动

### 第一次启动

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

### 日常使用

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

Compose 不再要求仓库根目录存在 `.env`，默认只把 Nginx 绑定到本机 `127.0.0.1:3015`，后端端口不会直接暴露。需要联网检索或模型密钥时，在当前终端设置对应环境变量后再启动；不要把密钥写入 Git 跟踪文件。

数据库、上传文件、静态产物、笔记结果、向量索引和运行配置都保存在命名卷 `fastread-data`。升级镜像或重建容器不会删除该卷；删除卷会永久删除这些运行数据。

Docker 模式的访问地址仍是：

```text
http://127.0.0.1:3015/
```

单镜像部署使用 `Dockerfile.complete` 时，持久化目录是 `/var/lib/fastread`：

```powershell
docker build -f Dockerfile.complete -t fastread:local .
docker run -d --name fastread -p 127.0.0.1:3015:80 -v fastread-data:/var/lib/fastread fastread:local
```

## 常见问题

如果提示找不到 `backend\.venv`，先按 README 创建后端虚拟环境并安装依赖。

如果提示找不到 `fastread-frontend\node_modules`，先进入前端目录执行 `corepack enable` 和 `pnpm install`。

如果提示端口被占用，默认前端端口是 `3015`，后端端口是 `8483`。可以打开 `.env`，修改 `VITE_FRONTEND_PORT` 或 `BACKEND_PORT`，再重新启动。

如果页面能打开但近邻论文检索失败，优先检查：

- 设置页里是否配置了模型供应商和模型。
- Scholar 等外部检索提供方是否已配置；未配置时页面会显示明确状态并继续返回其他来源。
- 后端日志里是否出现检索提供方失败或本地索引不可用等信息。
- `run.bat --status` 的健康检查是否成功。

如果你正在使用 Docker 可选路径，才需要检查 Docker Desktop 是否启动、`docker compose ps` 是否正常。
