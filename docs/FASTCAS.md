# 可选 FastCAS 接入（首轮实现）

本地密码、邀请注册和 Research 票据入口继续可用。FastCAS 绑定原用户 ID，保留工作区与 ACL；没有绑定时不会按邮箱合并或创建账号。新用户遵循项目邀请政策，先注册本地账号，再主动认证。

## 开发配置

在 FastRead 根目录运行 `python -m pip install -r requirements-fastcas.txt`，使用同级 FastCAS 的 Python SDK。部署发布版 SDK 的安装方式待统一发布工作完成。本地模式不需要 SDK，不会访问 FastCAS。

连接配置四项必须同时提供：

- `FASTREAD_FASTCAS_ISSUER`：FastCAS origin。
- `FASTREAD_FASTCAS_CLIENT_ID`：此实例登记的 client ID。
- `FASTREAD_FASTCAS_CLIENT_SECRET`：服务端凭证。
- `FASTREAD_FASTCAS_REDIRECT_URI`：精确回调，例如 `https://read.example.com/api/auth/fastcas/callback`。

仅环回 HTTP 开发可设置 `FASTREAD_FASTCAS_ALLOW_LOOPBACK_HTTP=true`，同时配置 `FASTREAD_COOKIE_SECURE=false`。生产使用 HTTPS。应用登记 scopes 为 `openid profile email`，事件端点为 `/api/auth/fastcas/events`。同实例外部 Origin 必须与回调的 origin 一致，前端和 API 同源部署。

## 用户流程

登录页增加“使用 FastCAS 登录”；账号设置可认证、重试 prepared 关系或解除认证。绑定与解除需要当前项目会话、CSRF 和本地密码。通过 FastCAS 回来只签发项目 HttpOnly 会话，令牌不交给浏览器。

旧 Research 账号可从原入口重新登录，在五分钟内于账号设置补充本地邮箱和密码，再进行 FastCAS 认证。已有本地密码则必须提供原密码才能更改。设置保留用户和工作区，撤销其他会话；后续 Research 登录保留设置的邮箱，也不撤销本地会话。

本地登录后认证不会改变该会话来源。FastCAS 登录会话每五分钟最多复核一次有效绑定，过期且中心不可用时拒绝该来源访问，用户可用本地方式登录。签名撤销事件即时撤销对应 CAS 来源会话，不删除本地用户或数据。未知来源的事件在 SDK 验签之前不会写数据库。

## API

`/api/auth/fastcas` 下提供 GET `available`、`login`、`callback`、`status`；POST `link`、`reconcile`、`revoke`、`events`。link/revoke 接受 `{password}`；reconcile 使用当前账号的 prepared 映射。events 只接受最大 64 KiB 的 `application/jwt`，由 SDK 校验 issuer、audience、签名、类型和期限，应用原子提交去重、版本检查、绑定更新和会话撤销。

## 验证和剩余工作

`PYTHONPATH=backend python3 -m pytest --noconftest backend/tests/test_local_accounts.py backend/tests/test_fastcas_store.py backend/tests/test_fastcas_service.py -q`：16 项通过。跳过全局桌面数据库 fixture，仅验证账号和接入服务；不代表全仓库回归。

FastCAS 根目录运行 `FASTCAS_PROJECT_CONTRACT=1 go test ./internal/httpapi -run '^TestFastReadAgainstProvider$' -count=1 -v`，需要测试 PostgreSQL 和可导入 FastAPI、HTTPX、SDK 的 Python（可用 `FASTCAS_PROJECT_PYTHON` 指定）。已通过真实 Go 提供方 + PostgreSQL + Python SDK + FastRead 真实认证路由契约，覆盖同邮箱不合并、本地证明绑定、CAS 登录、回调重放拒绝、解除后保留本地会话和原论文工作区。

签名绑定/身份状态事件与 back-channel logout 路由现使用 Python SDK 的可选 FastAPI 适配层处理消息类型、大小限制、验签及失败重试响应；本项目 SQLite 事务仍负责事件 ID 去重和仅撤销 FastCAS 来源会话。真实提供方的退出与身份状态投递契约已通过。

网络恢复后在 fastread-frontend 使用 `corepack pnpm install --frozen-lockfile` 安装成功；`corepack pnpm run typecheck`、`corepack pnpm run build` 和 `corepack pnpm run test` 全部通过（18 个文件、71 项测试）。真实浏览器联调发现并修复无会话时启动脚本强制跳转旧 Research 门户的问题；现在本地密码/邀请与 FastCAS 登录入口均可进入。Chrome/真实 FastAPI/SQLite/Go FastCAS/PostgreSQL 契约完成本地登录、显式绑定、独立浏览器 FastCAS 登录、原论文与工作区保持、解绑仅撤销 CAS 会话；race 模式连续三次通过。

尚待：完整后端应用依赖安装后的全路由回归、正式域名浏览器检查、生产迁移与部署演练；上游退出通知已接入，真实跨进程投递契约已通过。

恢复边界补测：远端解绑已提交但响应丢失时，重试先读取当前版本并完成本地撤销；激活旧响应不能把已撤销绑定显示为成功；对账遇到远端撤销会原子删除该绑定的 CAS 会话。

FastCAS 应用登记还需设置 `backchannel_logout_uri` 为 `/api/auth/fastcas/backchannel-logout`。接收端验证标准签名 `logout_token`，按身份及可选 sid 原子去重，只撤销 FastCAS 来源会话；项目本地登录、账号、内容和权限保持独立。

`events_uri` 同时接收签名 `identity.status_changed` 通知。中心停用只终止对应 FastCAS 来源会话，重新启用不恢复旧会话；本地登录、工作区与论文数据不受影响。真实提供方到 FastRead 接收端的状态事件契约已通过。
