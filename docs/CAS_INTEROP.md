# News → Read → Write 的 CAS 互通

三端使用已有的本地账号、CAS 绑定和项目权限。用户在各端认证同一 CAS 身份，在 FastRead「设置 → 应用联动」点击「通过 CAS 连接 FastNews / FastWrite」，即可使用既有同步能力，无须复制连接码。手动连接方式仍可使用。

## 阅读与写作链路

1. FastNews 论文上的阅读入口携带论文元数据进入 FastRead。本地账号现在也可交接；已绑定 CAS 的账号使用 `auth=cas` 进入登录流程，不再要求旧 Research 票据。未启用 CAS 时保留本地登录。旧 Research 入口继续工作。
2. 论文在 FastRead 按来源 ID 去重收录，PDF、版本化页码证据、报告、批注与主笔记沿用原阅读链路。
3. 选中论文后交接 FastWrite：元数据、阅读报告、逐字引文、批注、个人笔记与 BibTeX 形成不可变资料包，只允许写入用户有权限的项目及路径。相同资料重复上传不会产生副本；冲突不会覆盖原文件。成功后可直接打开写作项目。
4. FastWrite「文献与证据」可打开关联论文原文、保存写作反馈。FastRead 的「取回写作笔记」按项目、原论文和反馈 ID 更新笔记，重复拉取不会重复新增。证据的审阅状态和引用立场也随反馈返回。
5. 阅读提炼出的研究方向可追加或替换 FastNews 当前账号的个人印象，供后续检索使用。

CAS 登录返回后保留原论文、知识库或设置入口。跳转只恢复白名单内的本应用参数，状态仅保存在当前浏览器标签页，十分钟后过期。

## 部署配置

三个应用需配置同一 FastCAS issuer，并保留各自的交互登录 client ID 和密钥。

在 FastCAS 控制台「服务身份」登记独立服务客户端：

- 客户端 ID：`fastread-sync`。
- grant：仅 `client_credentials`。
- scope：`fastread:connect`。
- resources：FastNews 和 FastWrite **实际配置的 CAS client ID**（例如 `news`、`fastwrite`）。

将该服务身份的密钥仅配置到 FastRead 后端的 `FASTREAD_SYNC_CLIENT_SECRET`。不要将交互登录客户端改为服务身份。未配置服务密钥时不显示 CAS 一键连接按钮，手动连接仍可用。

地址配置：

| 应用 | 配置 | 用途 |
| --- | --- | --- |
| Read | `FASTREAD_FASTNEWS_URL`、`FASTREAD_FASTWRITE_URL` | 服务端接口地址 |
| Read | `FASTREAD_FASTNEWS_PUBLIC_URL`、`FASTREAD_FASTWRITE_PUBLIC_URL` | 浏览器公开入口 |
| News | `FASTREAD_URL` | 阅读及连接入口，支持部署路径前缀 |
| Write | `FASTWRITE_FASTREAD_PUBLIC_URL` | 阅读及连接入口，默认 `https://read.fastrd.io` |

CAS 服务身份的生产登记与密钥需由部署方配置。本次仓库验证不代表已经登记生产授权。

## 身份与撤销

FastRead 从当前已认证用户的本地 CAS 绑定取 subject，不接受浏览器指定另一身份。接收端校验 SDK 签名、issuer、目标 audience、服务客户端、scope 和中心实时 token 状态，再核对相同 subject 的本地与中心绑定。缺失绑定时不按邮箱合并，也不自动开户。

连接凭证只在服务端传递：Read 加密保存，News / Write 保存摘要。凭证固定账号、CAS 绑定 ID 与版本；每次访问复核绑定。解绑、重新绑定或停用账号后旧凭证不能恢复使用。Write 的 CAS 连接不会继承平台管理员权限，仍须拥有项目成员权限及路径权限。应用中的撤销连接、手动轮换功能继续可用。

新增服务接口 `POST /api/integrations/fastread/cas-connect` 仅接受 `fastread-sync` 的授权服务令牌和 `{subject}`，返回的凭证供 Read 后端保存，不返回浏览器。用户点击的 Read 接口为 `POST /api/integrations/connections/{fastnews|fastwrite}/cas`，要求工作区所有者会话和 CSRF。

## 验证

- Read：`go test ./...`；前端类型检查、Lint、单元测试及 reader、reading-studio、FastUI、CAS 入口浏览器测试。
- News：`go test ./internal/httpapi ./internal/store`，覆盖本地与 CAS 元数据交接、服务身份、错误 audience/scope、解绑及重绑拒绝；前端构建。
- Write：`bun test apps/server/src/auth/fastread-cas.test.ts apps/server/src/research/fastread-integration.test.ts`，覆盖身份隔离、凭证撤销、项目及路径权限、重复上传和反馈回传；前后端类型检查及前端构建。

应用侧 CAS 用例使用隔离的 SDK fixture；生产 CAS、跨域会话与实际部署地址仍需部署环境联调。
