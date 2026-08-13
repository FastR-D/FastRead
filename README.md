<p align="center">
  <img src="./doc/icon.png" alt="FastRead Logo" width="72" height="72" />
</p>

<h1 align="center">FastRead</h1>

<p align="center">
  <strong>NotebookLM 式学术阅读报告 + 可审计证据层</strong>
</p>

<p align="center">
  FastRead 优先解决“如何读懂一篇论文”：导入 PDF、围绕关键问题解释方法与贡献、保留页码引用、支持 300 字个人总结和持续追问；联网核验作为证据层保留。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/frontend-React%2019-61dafb" alt="React" />
  <img src="https://img.shields.io/badge/backend-FastAPI-009688" alt="FastAPI" />
  <img src="https://img.shields.io/badge/extension-Vue%203-42b883" alt="Vue" />
  <img src="https://img.shields.io/badge/AI-OpenAI%20%7C%20DeepSeek%20%7C%20Qwen-ff69b4" alt="AI Providers" />
</p>

---

## 目录

- [项目亮点](#项目亮点)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [测试](#测试)
- [使用流程](#使用流程)
- [主要接口](#主要接口)
- [配置说明](#配置说明)
- [浏览器扩展](#浏览器扩展)
- [常见问题](#常见问题)
- [项目结构](#项目结构)
- [路线图](#路线图)
- [相关文档](#相关文档)

## 项目亮点

FastRead 当前的 P0 是完成一篇论文的可审计阅读闭环：

```text
检索论文 / PDF / 论文 URL -> 分页原文 -> 关键问题报告 -> 方法与贡献 -> 300 字总结 -> 带页码持续追问 -> 一键导出 PPT
```

- **限定会议检索**：只搜四大安全顶会（IEEE S&P、USENIX Security、ACM CCS、NDSS）与系统顶会（OSDI、SOSP、ASPLOS、EuroSys、USENIX ATC、SIGCOMM、NSDI、FAST）的论文，命中后可一键导入阅读。会议无法确认的论文单独列出，不混入结果。
- **NotebookLM 式报告**：固定覆盖研究问题、方法过程、主要贡献、实验/证据和局限，避免零散 bullet 堆砌。
- **结构化引用**：报告引用只有在分页原文或已抽取核验证据中匹配成功才会保留。
- **学术身份 Gate**：区分正式论文、预印本、身份不完整和撤稿；四大安全顶会须由抓取到的官方出版记录对齐标题、作者、年份、venue 和 DOI/官方 URL，用户填写的字段不能直接过 Gate。
- **个人总结**：AI 报告之外单独保存用户自己的 300 字内总结。
- **持续追问**：论文分页原文、阅读报告和核验证据共同进入任务问答上下文，来源显示页码。
- **一键生成 PPT**：把阅读报告投影成 `.pptx`（标题页、概览、逐个关键问题、方法过程、主要贡献、局限、术语、可追问清单），引文页码一并带入幻灯片。

联网核验仍是报告的证据层，规则不降级：

当前核验链路：

```text
输入文本/URL/已有任务 -> 主张原子化 -> 多查询检索 -> 正文/PDF 抓取 -> 信源验真 -> 证据抽取 -> 规则判定 -> 审计报告
```

- **主张原子化**：从输入文本、URL 正文或已导入论文中提取可核验的 atomic claims。
- **多源联网检索**：支持 Brave、Bing Academic、Bing CN、Baidu 等搜索源和质量补充检索。
- **正文证据优先**：搜索摘要只作为召回线索；`supported` 必须来自抓取到的网页/PDF 正文证据。
- **信源验真**：输出来源等级、canonical URL、publisher、author、published date、content hash、independence group、redirect chain 和风险标记。
- **反操纵防线**：识别伪权威域名、canonical/redirect 异常、提示词注入、内容农场、榜单软文、复制转载和缺失来源身份。
- **可恢复任务**：持久化 claim 级中间产物，rerun 默认只重试失败或未完成的 web 阶段。
- **缓存与审计**：SERP、snapshot、evidence 缓存会记录 hit/miss，方便复查任务为什么得到某个结论。
- **规则判定**：最终 verdict 来自规则证据矩阵，不允许 LLM 自由判断覆盖证据。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| Web 前端 | React 19、Vite、TypeScript、Tailwind CSS、Radix UI、Zustand、Markmap |
| 后端服务 | Python、FastAPI、SQLAlchemy、SQLite、Uvicorn |
| 论文解析 | PyMuPDF（分页正文）、python-pptx（幻灯片导出） |
| 检索 | arXiv API、本地倒排索引（Elasticsearch 预留可替换） |
| 浏览器扩展 | Vue 3、Vite、WebExtension MV3、UnoCSS |
| 桌面端预留 | Tauri 2 |
| AI 能力 | OpenAI Compatible API、DeepSeek、Qwen |
| 部署 | 本地 Windows 启动脚本、可选 Docker Compose/Nginx |

## 快速开始

### 给非技术人员

Windows 上只保留根目录一个入口：

```text
run.bat           启动本地后端和前端
run.bat --status  查看服务状态和健康检查
run.bat --stop    停止本地前后端进程
run.bat --check   检查本地依赖
```

第一次启动前需要准备好 `backend\.venv` 和 `fastread-frontend\node_modules`。详细说明见 [笨蛋部署说明](./DEPLOYMENT.md)。

### 方式一：本地脚本启动（推荐）

Windows 用户优先双击根目录的 `run.bat`。这是唯一保留的本地入口，默认不需要 Docker。

默认访问地址：

```text
http://127.0.0.1:3015/
```

后端 API：

```text
http://127.0.0.1:8483/api/sys_check
http://127.0.0.1:8483/api/sys_health
```

如果只想启动但不自动打开浏览器：

```powershell
.\run.bat --no-open
```

脚本会自动：

- 读取或创建本地 `.env`
- 检查后端虚拟环境和前端依赖
- 启动后端和前端开发服务
- 通过健康检查后打开浏览器

首次运行前如果依赖不存在，先安装：

#### 准备后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
```

#### 准备前端

```powershell
cd fastread-frontend
corepack enable
pnpm install
cd ..
```

### 方式二：手动源码开发启动

如果需要分别调试后端或前端，可以手动启动。默认仍建议使用和 `run.bat` 一致的本地端口：

- 后端：`http://127.0.0.1:8483`
- 前端：`http://127.0.0.1:3015`

启动后端：

```powershell
cd backend
.\.venv\Scripts\python.exe main.py
```

启动前端：

```powershell
cd fastread-frontend
$env:VITE_API_BASE_URL="/api"
pnpm run dev -- --host 0.0.0.0 --port 3015
```

后端根路径不是页面入口，直接访问 `http://127.0.0.1:8483` 返回 `{"detail":"Not Found"}` 属于正常现象。

### 可选：Docker 部署路径

Docker 仅作为可选部署或高级演示路径保留，不再是默认推荐启动方式。确实需要容器部署时，直接使用 Docker Compose：

```powershell
docker compose up -d --build
```

Docker 模式下，后端通过 Nginx 的 `3015` 端口访问：

```text
Web:      http://127.0.0.1:3015/
API:      http://127.0.0.1:3015/api/...
健康检查: http://127.0.0.1:3015/api/sys_check
```

查看服务状态和日志：

```powershell
docker compose ps
docker compose logs --tail=80 backend
```

停止 Docker 服务：

```powershell
docker compose down
```

如果本地还残留旧容器名，执行一次完整重建即可切换到 `fastread-backend`、`fastread-frontend`、`fastread-nginx`：

```powershell
docker compose down
docker compose up -d --build
```

## 测试

后端测试依赖单独放在 `backend/requirements-dev.txt`。首次配置测试环境：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd ..
```

从仓库根目录运行后端测试：

```powershell
backend\.venv\Scripts\python.exe -m pytest
```

前端和扩展构建检查：

```powershell
cd fastread-frontend
pnpm run build

cd ..\fastread-extension
pnpm run build
```

## 使用流程

### 论文阅读主流程

1. 在资料库点击「论文检索」，按关键词搜索四大安全顶会与系统顶会论文；或直接点「导入论文」上传 PDF / 粘贴论文 URL。
2. 打开「全文」，先确认页数、正文和来源是否正确。
3. 点击「一键生成阅读报告」，检查关键问题、方法过程、主要贡献、证据与局限。
4. 逐条核对报告引文的页码是否与分页原文一致。
5. 写下不超过 300 字的个人总结。
6. 用「继续追问」围绕当前论文提问，并检查回答给出的页码。
7. 需要对外汇报时，点「导出 PPT」把报告投影成幻灯片。
8. 只有需要外部支持、反证或信源审计时，再进入可选证据层。

### 联网核验流程（证据层）

1. 打开 Web 前端。
2. 输入待核实文本、URL 或选择已有任务。
3. 点击发起联网核实。
4. 等待任务完成主张提取、检索、抓取、证据抽取和交叉判定。
5. 在报告中查看整体状态、claim verdict、confidence、正文证据、来源等级、风险标记和 audit。
6. 对失败或不完整的任务点击 rerun；默认只重试失败/未完成 web 阶段。

生成结果默认写入：

```text
backend/note_results/
```

常见结果文件：

```text
{task_id}.json
{task_id}.status.json
{task_id}_markdown.md
{task_id}_markdown.status.json
_verification/{task_id}/claims/{claim_id}.json
_verification/_cache/serp/*.json
_verification/_cache/snapshot/*.json
_verification/_cache/evidence/*.json
```

检索索引缓存写入：

```text
backend/data/paper_search_index.json
```

## 主要接口

论文阅读：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/papers/search` | 限定会议的论文检索；返回命中结果与被排除的 `venue_unconfirmed` |
| `GET` | `/api/papers/search/venues` | 当前生效的会议白名单，用于构建筛选 UI |
| `POST` | `/api/papers/from_url` | 从论文详情页 / PDF URL 导入 |
| `POST` | `/api/papers/upload` | 上传本地 PDF 导入 |
| `POST` | `/api/reading_reports` | 一键生成关键问题阅读报告（`force=true` 重新生成） |
| `PUT` | `/api/reading_reports/{task_id}/personal_summary` | 保存 300 字个人总结 |
| `GET` | `/api/reading_reports/{task_id}/pptx` | 导出阅读报告为 `.pptx` |
| `POST` | `/api/chat/ask` | 基于分页原文的持续追问，返回带页码的 sources |

检索请求示例：

```bash
curl -X POST http://127.0.0.1:8483/api/papers/search \
  -H "Content-Type: application/json" \
  -d '{"query":"side channel attack","tracks":["security"],"limit":10}'
```

响应中的 `search_backend`、`elasticsearch_available`、`venue_unconfirmed_count`
用于说明本次检索的真实覆盖范围，避免把「结果少」误当成「该领域没有论文」。

## 配置说明

主要配置位于根目录 `.env`。

| 变量 | 说明 | 示例 |
| --- | --- | --- |
| `APP_PORT` | 可选 Docker/Nginx 对外端口 | `3015` |
| `BACKEND_HOST` | 后端监听地址 | `0.0.0.0` |
| `BACKEND_PORT` | 后端服务端口 | `8483` |
| `VITE_API_BASE_URL` | 前端请求后端 API 地址 | `/api` 或 `http://127.0.0.1:8483/api` |
| `NOTE_OUTPUT_DIR` | 任务结果、核验产物和缓存目录 | `note_results` |
| `DATA_DIR` | 检索索引等本地数据目录 | `data` |
| `PAPER_SEARCH_SECURITY_VENUES` | 安全会议白名单（留空为四大） | `ieee_sp,usenix_security,acm_ccs,ndss` |
| `PAPER_SEARCH_SYSTEMS_VENUES` | 系统会议白名单（留空为全部内置） | `usenix_osdi,acm_sosp,asplos` |
| `PAPER_SEARCH_TIMEOUT` | 论文检索超时（秒） | `12` |
| `PAPER_SEARCH_FETCH_LIMIT` | 单次检索抓取上限 | `80` |
| `ONLINE_VERIFY_SEARCH_PROVIDER` | 联网核验主搜索源 | `brave`、`bing_academic`、`bing_cn` |
| `ONLINE_VERIFY_SEARCH_FALLBACK_PROVIDERS` | 联网核验兜底搜索源 | `bing_academic,bing_cn,baidu` |
| `BRAVE_SEARCH_API_KEY` | Brave Search API Key | 使用 Brave 搜索源时填写 |
| `BRAVE_SEARCH_COUNTRY` | Brave 搜索国家/地区 | `CN` |
| `BRAVE_SEARCH_LANG` | Brave 搜索语言 | `zh-hans` |
| `BRAVE_SEARCH_UI_LANG` | Brave 搜索界面语言 | `zh-CN` |

### 论文检索范围如何调整

会议白名单在 `backend/app/services/academic_evidence.py` 中定义（`TOP_SECURITY_VENUES` 与 `SYSTEMS_VENUES`），
可通过上面两个环境变量按 venue id 收窄。例如只保留 OSDI：

```env
PAPER_SEARCH_SYSTEMS_VENUES=usenix_osdi
```

检索当前使用 arXiv API 作为语料源、本地倒排索引做打分。Elasticsearch **尚未接入**，
接口响应里的 `search_backend` 和 `elasticsearch_available` 会明确报告这一点；
`InvertedIndex` 的接口按 ES 语义设计，组内部署时可直接替换为真实 ES 客户端。

## 浏览器扩展

扩展目录位于 `fastread-extension/`。当前可发布范围是 verification-first popup：从当前标签页 URL 或粘贴文本创建 FastRead 联网核实任务，并打开 Web 工作台报告。

安装依赖：

```powershell
cd fastread-extension
pnpm install
```

开发构建：

```powershell
pnpm dev
```

生产构建：

```powershell
pnpm build
```

构建产物会输出到：

```text
fastread-extension/extension/
```

当前 manifest 只声明 popup；`background`、`contentScripts`、`options` 和 `sidepanel` 仍是后续完整扩展草稿，不属于当前发布产物。扩展默认连接：

```text
http://127.0.0.1:8483
```

创建任务接口：

```text
POST http://127.0.0.1:8483/api/verification_tasks
```

## 常见问题

### 页面一直显示后端初始化中

检查前端是否指向了正确后端：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8483/api"
```

修改后需要重启前端服务，并在浏览器中按 `Ctrl + F5` 强制刷新。

### 生成失败并提示第三方服务异常

通常是模型供应商或联网检索侧波动。检查：

- 模型供应商 API Key、Base URL 是否正确，额度是否用尽
- `BRAVE_SEARCH_API_KEY` 是否配置（联网核验需要）
- 后端日志中的具体异常

### 阅读报告生成失败

阅读报告要求引文能在分页原文中精确匹配，因此以下情况会直接失败而不是降级输出：

- 扫描版或加密 PDF 解析不出正文（当前未接入 OCR）
- 关键问题少于 4 个，或缺少方法过程 / 主要贡献
- 可匹配引文少于 3 条

### 检索结果偏少

检索只保留能从 arXiv `comments` / `journal_ref` 中确认属于白名单会议的论文。
未标注会议的论文会计入 `venue_unconfirmed` 并在界面上单独展开，不会混入正式结果。
放宽范围可以取消勾选会议筛选，或改用 PDF / URL 直接导入。

### 可选 Docker 服务启动后无法访问

确认端口没有被占用，并查看服务状态：

```powershell
docker compose ps
docker compose logs --tail=80
```

Docker 正常时，宿主机健康检查应返回 `{"code":0,"msg":"success","data":null}`：

```powershell
Invoke-RestMethod http://127.0.0.1:3015/api/sys_check
```

## 项目结构

```text
.
├── backend/                # FastAPI 后端：论文解析、阅读报告、PPT 导出、论文检索、证据审计
│   ├── app/services/       #   paper_ingest / reading_report / ppt / paper_search / verification
│   ├── app/routers/        #   note（论文与报告）、chat（追问）、model、provider、config
│   └── note_results/       #   任务产物与缓存
├── fastread-frontend/      # React Web 前端（资料库、检索、阅读工作台）
├── fastread-extension/     # 浏览器扩展
├── doc/                    # 文档图片和产品资料
├── docs/                   # 产品需求文档
├── nginx/                  # Docker 反向代理配置
├── docker-compose.yml      # Docker Compose 部署
├── OPEN_ME_FIRST.md        # 给非技术人员的最短说明
├── run.bat                 # 唯一 Windows 本地入口：启动/检查/状态/停止
├── pytest.ini              # 后端 pytest 配置
└── DEPLOYMENT.md           # 面向非技术人员的部署说明
```

## 路线图

论文阅读（P0，已完成）：

- [x] PDF / URL 逐页解析与持久化
- [x] 一键关键问题阅读报告（研究问题、方法过程、主要贡献、实验证据、局限）
- [x] 报告引文与分页原文精确匹配，匹配不上即丢弃
- [x] 300 字个人总结独立保存
- [x] 单篇论文页码感知持续追问
- [x] 学术身份 Gate 与外部证据层分离
- [x] 阅读报告一键导出 `.pptx`
- [x] 四大安全顶会 + 系统顶会限定检索（arXiv 语料 + 本地倒排索引）

证据层（已完成）：

- [x] Verification-first 任务 API
- [x] Claim 级中间产物持久化
- [x] SERP、snapshot、evidence 缓存和 cache audit
- [x] 来源等级、独立性、canonical、content hash 和 redirect chain audit
- [x] 伪权威、canonical/redirect 异常、prompt injection、内容农场和复制转载风险
- [x] GEO/language differential retrieval 骨架和 `geo_disagreement`

仍在路线图中：

- [ ] Elasticsearch 接入，替换本地倒排索引（组内部署）
- [ ] 检索语料扩展到 DBLP / 会议官方目录，不再依赖 arXiv 的会议标注
- [ ] 扫描版 PDF 的受控 OCR
- [ ] 论文页内高亮与引用跳转
- [ ] 抽象摘要的 LLM 关键词增强（当前为启发式抽取）
- [ ] Source registry 外置为可维护文件或表
- [ ] 更强 publisher/author/date 抽取与来源身份评分
- [ ] 单 claim / 单 stage 更细粒度 rerun
- [ ] 前端报告强化筛选：高风险、证据不足、refuted、data void、domain、source tier
- [ ] 浏览器扩展完全转为「用 FastRead 阅读/核实此论文」
- [ ] 更完整的端到端回归测试

## 相关文档

- [产品需求文档](./docs/FASTREAD_REQUIREMENTS.md)
- [部署说明](./DEPLOYMENT.md)
