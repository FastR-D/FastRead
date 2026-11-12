# Go 迁移验证

验证日期：2026-11-12。目标版本：FastRead 4.0.0。

生产 SQLite 通过只读连接和 SQLite backup API 复制到隔离目录，随后由 Go `OpenStore` 打开快照并完成结构初始化。验证仅在快照启动 API，原库与原 PDF 保持只读，未启动任务 worker。

## 数据保留

35 张原表的记录数全部保持一致。SQLite `integrity_check` 返回 `ok`，迁移前后 `foreign_key_check` 均为 0 条异常。

| 原表 | 迁移前 | 迁移后 |
| --- | ---: | ---: |
| account_audit | 0 | 0 |
| account_credentials | 0 | 0 |
| conversations | 17 | 17 |
| document_versions | 24 | 24 |
| evidence_chunks | 2756 | 2756 |
| fastcas_events | 0 | 0 |
| fastcas_links | 0 | 0 |
| fastcas_transactions | 1 | 1 |
| jobs | 161 | 161 |
| knowledge_bases | 15 | 15 |
| knowledge_messages | 29 | 29 |
| knowledge_migrations | 1 | 1 |
| knowledge_papers | 28 | 28 |
| legacy_archive | 16 | 16 |
| login_attempts | 2 | 2 |
| memberships | 23 | 23 |
| messages | 25 | 25 |
| migration_records | 4 | 4 |
| notebook_notes | 0 | 0 |
| pages | 480 | 480 |
| paper_identities | 32 | 32 |
| paper_insights | 18 | 18 |
| paper_tags | 95 | 95 |
| papers | 25 | 25 |
| provider_cache | 4 | 4 |
| provider_cooldown | 1 | 1 |
| providers | 4 | 4 |
| reading_annotations | 3 | 3 |
| report_versions | 7 | 7 |
| schema_versions | 1 | 1 |
| sessions | 3 | 3 |
| topic_evidence | 13 | 13 |
| topics | 1 | 1 |
| users | 22 | 22 |
| workspaces | 21 | 21 |

以下关系在迁移前后均无异常：论文的当前版本归属、版本的论文归属、页码的版本归属、报告版本与论文对应、批注页码与版本对应、论文笔记与知识库笔记的归属、知识库成员的工作区归属、会话原文版本与工作区归属。

任务状态保持为 124 个 `succeeded`、31 个 `failed`、6 个 `needs_attention`。快照时没有 `queued` 或 `running` 任务。

## 读取接口与 React 数据结构

隔离库为各工作区创建临时验证会话，完成 322 次读取请求，全部返回 HTTP 200。验证结束后，临时用户、成员关系和会话全部移除，隔离 API 停止。

| 接口类别 | 请求数 |
| --- | ---: |
| 论文列表、知识库列表、任务列表、标签列表 | 各 21 |
| 论文详情 | 25 |
| 分页原文、批注 | 各 22 |
| 报告列表、会话列表、论文笔记、近邻论文 | 各 25 |
| 论文会话消息 | 17 |
| 历史报告详情 | 7 |
| 知识库详情、知识库消息、知识库笔记 | 各 15 |

全部 7 份历史报告的关键问题、方法过程、贡献及引文结构满足 React 阅读组件的对象与数组约定。54 条历史消息的证据对象、来源列表、页码及引文可直接读取；论文详情的元数据、版本、标签与知识库字段保持原协议。

原 Python Web 路由通过 AST 提取，共 68 个 HTTP 方法与路径组合，包括 PDF 的显式 HEAD 以及注册、恢复入口。Go 全部提供对应路由。对 68 条旧路由逐一发起无凭证探测，结果为：4 个公开读取成功、57 个返回登录要求、3 个返回请求校验要求；关闭 CAS 配置时，4 个 CAS 入口返回原协议的“未启用 FastCAS”。没有缺失路由或方法不匹配。

## PDF

23 个已登记 PDF 路径全部位于资料目录内且文件存在，总计 43,929,425 字节。将一份代表 PDF 复制到隔离资料目录后验证：

| 请求 | 结果 |
| --- | --- |
| 已登录 `Range: bytes=0-63` | HTTP 206，64 字节，PDF 文件头和 Content-Range 正确 |
| 已登录 HEAD | HTTP 200，响应体为空 |
| 已登录 If-None-Match | HTTP 304 |
| 匿名 Range | HTTP 401 |
| 私有缓存策略 | `private, no-cache` |

## 阅读报告与交接

报告生成沿用均衡分页上下文：总预算 120,000 字，每页最多 8,000 字；关键问题为 4–8 个，问题、方法和贡献逐项绑定原文引文。30 页测试文档的所有页均进入上下文，字符总量符合预算。

Markdown 导出保留报告总览、个人总结、关键问题、重要性说明、方法过程、贡献、原文页码、局限、术语、建议追问与用户批注。原文引文保留源页面的大小写和换行，并支持原有 PDF 连字与断字的规范化定位。报告完整导出、引用定位和 FastWrite 证据包协议专项测试通过。

最终 Linux 验证使用 Poppler 的 `pdftotext` 与 `pdfinfo` 执行真实 PDF 提取；`go test -race -count=1 ./...` 和 `go vet ./...` 全部通过。

验证记录仅保存表计数、关系检查结果和请求状态。
