# FastRead 论文工作台结构性重构计划

日期：2026-08-28  
状态：仅完成计划，尚未实施  
适用仓库：`E:\C_Moved_From_C\Users\Lenovo\Desktop\fastread`

> 下个对话应首先阅读本文件。本计划在冲突处取代旧的“视频笔记优先”“联网核验优先”及“把联网核验保留为可选证据层”的方案。

## 一、最终产品边界

FastRead 只做论文阅读、论文检索与组内研究整理：

```text
PDF / 论文 URL
-> 分页原文与学术身份
-> 关键问题阅读报告
-> 方法与贡献
-> 近邻论文 / 相关工作
-> 300 字个人总结
-> 带页码持续追问
```

本轮重构作出三个不可逆的产品决定：

1. 彻底退役 ReelMind 时代的视频下载、视频转写、短视频平台、独立网页/文本核验和“证据审计任务”。
2. 将“联网核验”替换为“近邻论文 / 相关工作”：只做学术文献发现、相似性排序和来源展示，不判断论文主张为真、假、支持或反驳。
3. 安全、系统、AI 三类核心会议共享一个正式学术身份 Gate；`is_top4_security` 只保留为安全四大细分类，不再决定 A1 是否通过。

## 二、当前问题的代码与数据依据

### 2.1 旧产品并未真正退出

- 设置菜单仍包含“音频转写配置”和“下载配置”。下载页面继续读取抖音、B站、快手平台常量并维护 Cookie。
- 前端仍有 `audit` 提交模式、`evidence` 工作区、`VerificationReportView`、资料库“证据审计”标签和非论文任务展示。
- 后端仍暴露 `/verification_tasks` 创建、重跑、逐主张重跑和列表接口，并维护完整的检索、正文抓取、证据抽取、地理比较和裁决流水线。
- 浏览器扩展仍声明抖音、B站、快手站点权限，并保留平台识别、视频任务和联网核实入口。
- 默认数据库文件名仍是 `backend/reel_mind.db`；当前库中 `video_tasks` 有 10 条 `douyin` 记录。
- `backend/note_results` 当前包含 11 个抖音主结果及其音频/转写缓存、2 个独立核验结果和 1 个论文结果。`list_tasks()` 会把数据库任务与所有结果文件合并，因此旧记录会重新进入前端。
- 前端恢复逻辑会把无法识别为论文的服务端任务默认映射成 `douyin`，所以只隐藏页面或修改默认筛选无法解决残余复活。

### 2.2 旧联网核验天然慢且输出职责过重

当前路径对每条主张执行多查询、多搜索提供方补充、逐 URL 抓取、正文抽取、来源分级、证据判断、可选 GEO 分支和最终裁决。最坏情况接近：

```text
主张数 × 查询数 × 搜索提供方 × 抓取来源数
```

它同时要求模型理解上下文、改写查询并尝试裁决搜索结果。这个职责既慢，也容易把“找到相似材料”误表述成“主张已被支持或反驳”。

### 2.3 学术身份 Gate 目前处于部分修复状态

当前未提交代码已开始让安全、系统、AI 核心会议共享 Gate，并能从 EigenBench 首页识别 ICLR 2026 候选身份；但运行时数据、旧阅读报告文案、前端展示和会议记录解析还没有完成统一迁移。因此下一轮不能只改 Badge，必须同时修正持久化身份和基于旧 Gate 生成的报告内容。

## 三、下一轮的强制实施原则

### 3.1 禁止过度防御而逃避重构

下个对话禁止采用以下做法：

- 只隐藏旧菜单、旧标签或旧记录，但保留对应路由、API、服务、状态枚举和持久化读取路径。
- 给旧视频任务或旧核验任务增加更多过滤条件、兼容分支、功能开关或“暂时保留”逻辑。
- 用新的“近邻论文”名称包装原核验流水线，继续输出支持、反驳、置信度、信源等级或模型裁决。
- 保留 `online_verifier.py` 兼容门面、双写旧新结果结构、双读 `reel_mind.db` 与新数据库，或新增长期迁移兜底。
- 通过更宽泛的 `try/except`、静默失败或假成功来维持旧调用方。
- 只为当前 EigenBench 写特例，而不统一会议目录、身份状态机和解析接口。
- 为了“少改文件”而继续让 `NoteTaskService` 同时承担视频、核验、论文、近邻和资料库职责。

允许且只允许一个迁移期安全措施：执行数据迁移前制作一次带清单和哈希的只读快照。迁移成功后，运行时不得继续读取旧库和旧任务产物。

### 3.2 保留当前工作区，不做破坏性 Git 操作

- 当前工作区高度脏，并且 `main` 与远端已经分叉；不得 `reset --hard`、`checkout --`、覆盖未提交文件或先拉取远端。
- 先逐文件理解和继承当前学术检索、阅读报告、Evidence Hub 与 Gate 修改，再重构。
- 本计划不授权 commit、push、tag、Release 或 PR 操作。

## 四、目标架构

```text
PaperIngestService
├─ PaperDocumentRepository       分页原文、标题、作者、年份、来源锁定
├─ AcademicIdentityService       会议目录、正式身份闭合、完整性状态
├─ ReadingReportService          原文落页的阅读报告
└─ RelatedWorkService            论文主张锚点 -> 文献检索 -> 近邻排序
   ├─ CoreVenueProvider          安全 / 系统 / AI 核心会议
   ├─ ArxivProvider              arXiv 扩展
   ├─ ScholarProvider            Google Scholar 补充
   └─ PaperIndex                 Elasticsearch，缺席时本地倒排索引
```

必须拆开的两个概念：

- `AcademicIdentityService` 回答“这篇论文正式发表在哪里、身份是否闭合”。
- `RelatedWorkService` 回答“哪些论文与本文的研究问题、方法或贡献最接近”。

近邻结果不得反向决定学术身份，学术身份也不得被表述成论文内容正确性的证明。

## 五、工作包 A：退役 ReelMind 与旧数据根

### A1. 建立一次性迁移清单

在任何删除前，生成机器可读清单，至少记录：

- `reel_mind.db`、`bili_note.db` 的路径、大小、SHA-256 和表计数。
- `note_results` 中每个主结果的 `task_id`、类型、平台、关联缓存和修改时间。
- 上传 PDF、向量索引、核验缓存与浏览器本地任务状态的归属关系。
- 当前应保留的论文任务，特别是 EigenBench：`aa8c4d5e-c9bb-4c62-9308-a5522b7b0131`。

快照只用于可恢复迁移，不进入正常运行路径。

### A2. 建立论文专用数据根

- 默认数据库统一为 `fastread.db`，删除代码中的 `reel_mind.db` 和 `bili_note.db` 回退名称。
- 将 `video_tasks` 改为论文语义明确的持久化结构；不要继续复用 `video_id`、`platform`、`video_url` 字段承载论文。
- 只迁移仍有用途的数据：模型/provider 配置、论文任务、论文上传、阅读报告、个人总结、专题库、候选论文、FastWrite 交接。
- 不迁移视频任务、视频缓存、独立核验任务和核验缓存。
- 迁移完成后，`/api/tasks` 只能返回论文任务；不能通过前端过滤来实现这一点。

### A3. 清理前端持久化残余

- 升级 Zustand/IndexedDB 持久化 schema 版本。
- 迁移时只保留服务端仍存在的论文任务 ID、论文阅读位置和论文收藏信息。
- 删除 `bilinote-onboarded` 等旧品牌键和旧视频/核验表单状态。
- 页面刷新、重启前后都不得重新出现旧任务。

## 六、工作包 B：从产品和代码中删除旧视频/核验系统

### B1. 前端

直接删除而非隐藏：

- 设置中的下载、Cookie、音频转写页面及路由。
- 抖音/B站/快手平台常量、图标、视频 Banner 和视频专用表单字段。
- `SubmissionMode = 'audit'`、独立网页/文本审计入口和对应模型要求。
- `ReadingViewMode = 'evidence'`、`VerificationReportView` 和全部重跑交互。
- 资料库 `all/audits` 分类、核验 Verdict、证据来源计数和非论文任务打开逻辑。
- 前端服务层中的 verification task API，以及 store 中核验任务恢复/重跑分支。

设置页最终只保留当前论文工作台真正需要的配置，例如 AI 模型、论文检索/外部连接、运行状态和关于页。

### B2. 后端

- 删除 `/verification_tasks`、旧 `/online_verify` 等独立核验 API。
- 从 `NoteTaskService` 移除创建、执行、重跑、逐主张重跑、阶段产物和关联核验任务逻辑；论文生命周期迁入语义明确的服务。
- 删除通用核验流水线的查询改写、搜索补充、GEO 比较、正文证据抽取、来源裁决和 verdict 代码。
- `verification/fetching.py` 中确实被论文导入需要的安全 URL/PDF 解析能力先迁到论文抓取模块，再删除核验命名和无关依赖。
- 删除视频下载、视频 URL 校验、视频任务 DAO、视频转写和旧笔记生成的运行时注册入口。
- 删除核验专用任务状态，如 `SEARCHING_WEB`、`FETCHING_SOURCES`、`EVALUATING_EVIDENCE`。

### B3. 浏览器扩展与发布面

当前扩展仍以短视频和独立核验为核心，不能只改标题继续发布。下一轮二选一，默认执行第一项：

1. 从当前构建/Release 中移除扩展，待以后按“导入当前论文页到 FastRead”重新设计；或
2. 在同一轮彻底改成只识别论文详情页/PDF URL 的轻量导入器，并移除所有视频站点权限、平台类型和 Cookie 配置。

不得发布一个仍请求抖音、B站、快手权限的 FastRead 论文扩展。

## 七、工作包 C：把联网核验重建为“近邻论文”

### C1. 产品语义

入口名称统一为“近邻论文”或“相关工作”，展示位置位于阅读报告的“方法与贡献”之后。它只给出：

- 近邻论文标题、作者、年份、会议/来源。
- 官方页、DOI、arXiv、PDF 等可用链接。
- 与本文哪一个研究问题、方法步骤或贡献锚点最接近。
- 重合关键词和可解释的相关度分数。
- 元数据来源及抓取时间。

明确不提供：`supported/refuted/mixed`、真假结论、置信度、来源 A/B/C/D 等级、GEO 分歧和模型裁决。

### C2. 主张锚点

锚点从已经落到原文页码的阅读报告中确定性产生：

- 研究问题：从关键问题中选择研究目标相关项。
- 方法：从 `process` 选择 1–3 个核心步骤。
- 贡献：使用 `contributions` 的标题和描述，并保留其原文页码证据。
- 兜底：标题、摘要、作者关键词和确定性关键词提取。

每个锚点保存 `anchor_id`、`kind`、`text`、来源报告版本和对应页码。没有落源的模型句子不得成为对外检索主张。

### C3. 检索与排序

- 复用并收敛现有 `PaperSearchService`，检索范围为安全核心会议、系统核心会议、AI 核心会议、arXiv 和 Google Scholar。
- 一篇论文最多形成 3 条去重查询；不是每条主张各跑多提供方和多语言分支。
- arXiv 与 Scholar 并行请求，使用一个总 deadline；不得串行叠加超时。
- 不抓取每个候选的全文，不运行 AI judge，不做支持/反驳证据抽取。
- 先用 Elasticsearch BM25；ES 不可用时使用本地倒排索引，并在 UI 如实标注检索后端。
- 排序建议：标题匹配权重 4、关键词权重 3、摘要权重 1，再结合锚点覆盖、核心会议优先级、年份和去重规则。
- AI 仅可在报告生成或离线索引阶段补充关键词；点击“找近邻”的在线路径不依赖模型，并始终有确定性关键词回退。

### C4. 性能目标

- 已缓存或已有本地索引：首屏结果目标不超过 300 ms。
- 冷检索：总体 deadline 8 s，任何单一提供方不得拖延整体完成。
- 一个提供方失败时返回其他来源与明确状态，不重试多轮，不转入模型猜测。
- 相同论文版本与锚点命中缓存；缓存键包含论文内容哈希、报告版本、锚点和检索配置版本。

### C5. 新数据契约

建议使用独立对象，禁止继续复用 `VerificationClaim`：

```text
RelatedWorkSnapshot
├─ paper_id / paper_content_hash
├─ report_version
├─ anchors[]
├─ neighbors[]
│  ├─ canonical_paper_id
│  ├─ title / authors / year / venue
│  ├─ doi / official_url / arxiv_url / pdf_url
│  ├─ matched_anchor_ids[]
│  ├─ overlapping_terms[]
│  ├─ relevance_score
│  └─ provenance
├─ provider_status
├─ search_backend
└─ generated_at
```

API 建议收敛为：

```http
POST /api/papers/{task_id}/related-work
GET  /api/papers/{task_id}/related-work
```

不再创建独立“核验任务”，近邻结果是论文任务的派生快照。

## 八、工作包 D：统一核心会议学术身份 Gate

### D1. 单一会议目录

建立唯一的结构化 venue catalog，后端解析、检索过滤、Gate、前端文案和测试全部使用它：

- 安全四大：IEEE S&P、USENIX Security、ACM CCS、NDSS。
- 系统核心会议：当前目录中的 OSDI、SOSP、ASPLOS、EuroSys、USENIX ATC、SIGCOMM、NSDI、USENIX FAST。
- AI 顶会：ICLR、ICML、AAAI、NeurIPS/NIPS、ACL。

新增、删除或改名会议只能修改此目录，禁止后端、前端和测试各维护一份硬编码名单。

### D2. 身份状态机

至少区分：

- `confirmed_core`：官方记录与标题、作者、年份、会议闭合；核心 Gate 通过，等级 A1。
- `claimed_core_unverified`：PDF 声明核心会议，但尚未匹配官方记录；显示候选会议、作者、年份和“待官方核验”，不伪装通过。
- `confirmed_formal_other`：正式但不在核心目录，等级 A2。
- `preprint`：可识别预印本，等级 B1。
- `incomplete`：有部分学术元数据但无法闭合。
- `retracted_or_withdrawn`：正式记录已撤回或撤稿，Gate 失败。

核心通过条件统一为：

```text
formal_identity_passed && venue.is_core
```

`venue.track` 可以是 `security | systems | ai`；`is_top4_security` 仅用于显示“安全四大”，不得再次成为总 Gate。

### D3. 身份解析责任

- PDF 首页声明只生成候选身份。
- 官方会议/出版社/DOI/OpenReview/proceedings 记录用于闭合身份。
- 第三方索引只能帮助发现官方记录，必须在 provenance 中如实说明，不能伪装成直接官方抓取。
- 标题、作者、年份和会议匹配使用确定性规范化与显式阈值；模型不参与是否正式发表的最终判定。
- 前端完整展示会议、年份、作者、正式记录 URL、身份来源、闭合状态和失败原因。

### D4. 修复现有 EigenBench 任务

对 `aa8c4d5e-c9bb-4c62-9308-a5522b7b0131` 做一次原子迁移：

- 更新 `paper_document`、`audio_meta`、`insights.academic_gate` 和 `reading_report.academic_gate`。
- 身份应显示 ICLR 2026、AI track、正式记录 URL和 A1 通过。
- 强制重生成或结构化修正旧报告，删除“不能视为正式 ICLR 论文”等已经失效的结论；不能只换 Badge。
- 页面刷新和服务重启后结果保持一致。

## 九、实施顺序

1. 冻结当前文件清单和数据清单，制作一次迁移快照；不改 Git 历史。
2. 定义论文专用持久化 schema、venue catalog、`RelatedWorkSnapshot` 和迁移规则。
3. 迁移论文数据到 `fastread.db`，验证 EigenBench 和模型配置后，切断旧数据库读取。
4. 删除前后端视频功能、独立核验任务和旧状态机；让编译错误暴露所有旧依赖并逐个清除。
5. 从旧 fetching 代码中提取论文导入需要的最小安全抓取能力，随后删除通用核验流水线。
6. 实现 `RelatedWorkService`、两个 related-work API、缓存与前端近邻论文视图。
7. 完成统一学术身份服务、会议目录、现有任务回填和报告一致性修复。
8. 清理扩展/Release 面、旧文档、旧测试和运行时产物。
9. 运行全量自动化与 Playwright Microsoft Edge 验收；通过前不得打包或发布。

不采用“先隐藏旧功能、以后再删”的两阶段做法。每个工作包完成时，旧入口和旧调用链应同时消失。

## 十、验证矩阵

### 10.1 静态退役检查

在活动源码、配置、测试和发布脚本中确认以下旧入口为零；迁移计划和一次性迁移清单除外：

- `ReelMind`、`reel_mind.db`、`bili_note.db`
- `douyin`、`bilibili`、`kuaishou`
- `create_verification_task`、`VerificationReportView`、`/verification_tasks`
- `SEARCHING_WEB`、`FETCHING_SOURCES`、`EVALUATING_EVIDENCE`
- 设置中的下载/Cookie/音频转写路由
- 扩展中的短视频 host permissions

### 10.2 后端

- 运行全量 pytest，并使用仓库内 `--basetemp`。
- 数据迁移测试覆盖：只迁论文、旧任务不复活、模型/provider 保留、重复迁移幂等、失败不切换活动库。
- `/api/tasks` 只返回论文；已退役 API 返回 404，而不是兼容响应。
- 近邻检索测试覆盖：查询上限、并行 deadline、缓存、去重、排序、ES 回退、provider 状态和无模型运行。
- 对安全、系统、AI 每一个 venue 做 Gate 参数化测试，并覆盖候选未闭合、预印本、撤稿和别名。

### 10.3 前端

- 运行 lint、typecheck、Vitest 和 production build。
- 静态文案测试保证旧品牌、旧平台、旧核验 verdict 和旧路由不会回归。
- store 迁移测试保证 IndexedDB 中的旧视频/核验任务不会在刷新后复活。
- 近邻论文视图测试来源、锚点、相关度、provider 降级和空结果状态。

### 10.4 Playwright Microsoft Edge

分别用干净状态和迁移后状态验收：

1. 设置中不再出现下载、Cookie、音频转写、B站、快手或抖音。
2. 资料库只出现论文记录，没有证据审计标签和旧 ReelMind 记录。
3. 导入 PDF 后能读取分页原文并生成报告。
4. EigenBench 显示 ICLR 2026、AI 顶会正式论文、A1 通过和正式记录链接，旧错误结论消失。
5. 点击“近邻论文”后在 deadline 内看到核心会议/arXiv/Scholar 结果或明确的 provider 状态；页面不出现真假裁决。
6. 刷新页面、切换论文、重启服务后数据和阅读位置一致。
7. 控制台错误、页面错误和异常 HTTP 请求均为零。

## 十一、完成定义

只有同时满足以下条件才算完成：

- 旧视频和独立核验能力从 UI、路由、API、服务、类型、数据库读取、扩展权限和发布脚本中真实删除。
- 活动数据库不再使用 ReelMind/BiliNote 命名或读取旧任务，资料库不会靠过滤器隐藏残余。
- “近邻论文”是一条小而清晰的元数据检索链，不含模型裁决和逐来源正文核验。
- 安全、系统、AI 核心会议使用同一 Gate；官方闭合即 A1，候选未闭合如实显示。
- EigenBench 现有任务和报告一致通过 ICLR 2026 身份验收。
- 自动化测试、构建、`git diff --check` 和 Edge 验收全部通过。
- 输出一份删除清单、迁移清单、验证证据和仍然存在的真实限制。

任何“旧代码仍在，只是暂时不可见”“为兼容先双写”“以后再统一”“模型大概能判断”的结果，都不满足本计划。
