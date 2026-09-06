# FastRead Web 候选部署与回滚

本目录对应独立候选，不能原地替换旧数据目录。后端入口为 `backend/main.py`，独立 worker 为 `python -m app.web.worker`。旧桌面路由不挂载，前端入口仅加载 WebApp。

## 构建与制品

在前端安装锁定依赖后运行 TypeScript 检查和 Vite build。执行 `python deploy/web/package.py --output <外部路径>/fastread-web.tar.gz`。脚本仅打包源码、测试、部署模板和前端 dist，输出文件清单；不包含 work、node_modules、虚拟环境、数据库、上传资料、会话、供应商密钥或 .env。不要把整个候选工作目录上传为发布制品。

候选复用了线上已安装 Python 依赖；`backend/requirements-candidate-linux.lock.txt` 记录实测解释器的包名和精确版本，不含配置和密钥。正式部署应在新的 Linux 虚拟环境安装该锁定清单，与候选解释器执行相同测试后再切换；新环境安装本身仍需部署时验收。不得写入旧 release 的 venv。前端 node_modules 若为 junction，禁止通过它安装或清理依赖。

## 配置与启动

1. 解包到独立版本目录，创建独立共享数据与兼容配置目录，权限设为 0700；配置文件设为 0600。
2. 按 `web.env.example` 配置根目录、HTTPS origin、Secure cookie。受限 arXiv gateway 设置沿用现有部署；配置值不要写进报告。
3. 离线运行 `python -m app.web.admin --help` 开户。生产环境无公开注册接口。供应商归属工作区，密钥用现有 secret store 加密；必须一并保护兼容目录内的加密 key。
4. 安装两个 systemd 模板前修正其中路径。API 仅监听 loopback，反向代理终止 HTTPS。API 与 worker 使用同一个新 Web 数据根。
5. 验证 `/api/health`、匿名资源请求 401、登录、工作区资源隔离、导入后台任务、报告、对话、原文及下载。页面关闭后任务由 worker 继续执行。

## 迁移

先在静止的旧源上用 SQLite backup API 生成快照，再复制 paper_results 和 uploads。不能仅复制使用中的 SQLite 主文件而忽略 WAL。迁移工具只读打开源 SQLite，写入不同目录的 Web 数据库：

```
python -m app.web.migrate --source <只读快照> --inventory
python -m app.web.migrate --source <只读快照> --root <新Web数据> --workspace <目标工作区ID>
```

核对源任务数、结果数、PDF、个人总结、报告、专题及证据条数，重复执行应不产生重复记录。未登记的孤立结果归档供复核；已转换专题可在 Web 中读取。其他非空历史表保存在 legacy_archive，不代表其所有旧功能已经重建。供应商 key 不自动分配。旧浏览器本地聊天需要来自原浏览器的显式导出，本次未取得这些资料，不能称为全部历史聊天已迁。

## 备份、回滚与最终切换

先进入维护窗口，停止新请求与 worker，再备份 Web SQLite、files 目录和兼容配置/加密 key。备份应完整复制到独立目录，校验 SQLite integrity_check、foreign_key_check、各表记录数与 PDF 可打开性。可重建向量库不作为正式证据源。

回滚演练使用第二份隔离副本：备份数据库，修改副本，恢复备份，复核记录、总结、证据和文件；不能在正式库上演练。已运行的计费请求若结果未知必须标记 needs_attention，不自动重放。恢复数据库不代表可以重新发送这些请求。

最终公网切换前，保存当前后端与前端 release 链接和 Nginx 配置；重新生成静止源快照、迁移、核对，再将 HTTPS 入口指向已验收的新 Web API 和 dist。旧 release、旧共享数据保留。若验收失败，入口恢复到记录的旧 release；新 Web 数据保留隔离供诊断，不反向覆盖旧库。切换后产生的新写入须另行处理，不能通过恢复旧快照静默丢弃。

2026-09-06 的执行范围仅独立候选；公网 `47.110.133.67:3015` 没有切换。候选 tunnel 的 HTTP/Secure=false 只适用于本地验收。
