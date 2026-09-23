# 独立账号入口（接入开发中）

FastRead 保留 Research 票据登录，同时恢复独立邮箱密码入口。匿名 HTML 请求直接显示项目登录页；资源 API 仍需有效项目会话。FastCAS 首轮接入见 [FASTCAS.md](FASTCAS.md)，仍有完整应用与界面验证待完成。

管理员可使用既有 `python -m app.web.admin` 创建本地账号，也可指定 `--action invite` 或 `--action recovery`，配合 `--root` 和 `--email` 生成一次性凭证。命令输出含凭证，应通过可信渠道交付目标用户；数据库仅存摘要，凭证一小时有效，同类新凭证立即替代旧凭证。恢复仅适用于已有本地密码的账号，不凭邮箱接管 Research 身份。

浏览器先 GET `/api/auth/session-init` 获取预登录 CSRF，再 POST `/api/auth/login`（email、password）、`/api/auth/register` 或 `/api/auth/recover`（token、password），请求头携带 `X-CSRF-Token`。注册仅允许管理员邀请，不开放无凭证注册。恢复保留用户 ID、工作区和内容，撤销该用户既有会话。生产使用 HTTPS；仅本地 HTTP 开发设置 `FASTREAD_COOKIE_SECURE=false`。

事务测试：`PYTHONPATH=backend python3 -m pytest --noconftest backend/tests/test_local_accounts.py -q`。使用临时 SQLite，当前 5 项通过，覆盖并发单次消费、凭证替代、恢复保持身份和工作区、旧会话失效，以及实际本地认证 HTTP 路由的 CSRF 和限流。新增会话来源字段以增量方式迁移，旧会话标为 legacy；本地登录标为 local，Research 登录标为 research。Research 重新登录不再撤销同一用户的 local 会话。此命令跳过仓库全局桌面数据库 fixture，不代表完整 Web 回归通过。

待完成：完整 Web 路由回归（旧强制 Research 跳转预期已更新但尚未执行）、前端构建及浏览器验证、Python SDK 接入、绑定与撤销界面、真实 FastCAS 提供方契约测试。目前依赖下载超时，完整应用环境尚未安装。

## FastCAS 持久化接入进度

`fastcas_store.py` 已提供 SDK TransactionStore 的 SQLite 适配，以及 prepared/active/revoked 绑定记录、同实例活跃账号唯一约束和撤销事件原子处理。事件入口必须先经 Python SDK 验签再调用 `apply_verified_event`，不能直接接受客户端 JSON。该模块现已接到登录、绑定、撤销和签名事件路由；实际进度与验证范围见 [FASTCAS.md](FASTCAS.md)。

验证命令：`PYTHONPATH=backend python3 -m pytest --noconftest backend/tests/test_local_accounts.py backend/tests/test_fastcas_store.py -q`。7 项通过，包括跨实例并发单次消费、提交故障回滚与重试、旧事件不撤销新绑定、本地会话保留。可选配置、SDK 回调和账号界面已加入，前端构建与完整 Web 回归仍待验证。
