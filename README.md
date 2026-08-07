<p align="center">
  <img src="./doc/icon.png" alt="FastRead" width="72" height="72" />
</p>

<h1 align="center">FastRead</h1>

<p align="center">
  <strong>从论文原文出发，把“读过”变成可回到页码核对的理解。</strong>
</p>

<p align="center">
  导入 PDF 或论文 URL，逐页阅读原文，生成关键问题报告，提炼方法与贡献，写下 300 字总结，并围绕同一篇论文持续追问。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License" />
  <img src="https://img.shields.io/badge/frontend-React%2019-61dafb" alt="React 19" />
  <img src="https://img.shields.io/badge/backend-FastAPI-009688" alt="FastAPI" />
  <img src="https://img.shields.io/badge/citations-page--aware-7c3aed" alt="Page-aware citations" />
</p>

## 一条主链读完一篇论文

```text
PDF / 论文 URL
        ↓
     分页原文
        ↓
   关键问题报告
        ↓
    方法与贡献
        ↓
   300 字个人总结
        ↓
  带页码持续追问
```

FastRead 将论文原文作为主工作区，而不是把搜索结果、模型常识或外部摘要当作论文内容。

| 环节 | FastRead 做什么 | 结果如何核对 |
| --- | --- | --- |
| 导入 | 接收本地 PDF、PDF URL 或可解析出 PDF 的论文详情页 | 保留来源 URL 与文档元数据 |
| 分页原文 | 按页抽取、保存并展示正文 | 所有后续引用都能回到具体页 |
| 关键问题 | 回答研究问题、方法过程、实验/证据与局限 | 逐字引文必须在标注页面中匹配 |
| 方法与贡献 | 分开呈现“怎么做”与“新增了什么” | 不把作者主张自动扩大为领域共识 |
| 个人总结 | 将用户自己的理解与 AI 报告分开保存 | 最多 300 字，便于形成真正的阅读结论 |
| 持续追问 | 优先以当前论文分页原文回答 | 实质结论显示页码；无支撑时说明证据不足 |

## 核心能力

- **分页优先**：论文正文按页持久化，阅读、报告和问答共享同一份原文基础。
- **固定问题框架**：报告集中回答研究问题、主要过程、主要贡献、实验依据和局限，减少零散摘要。
- **可追溯引用**：报告证据同时记录起止页码；无法在对应页面匹配的引文不会进入结果。
- **原文约束问答**：围绕单篇论文连续提问，答案尽量附带页码，不用模型常识填补原文空白。
- **个人理解沉淀**：提供独立的 300 字总结，不用 AI 报告替代用户自己的判断。
- **失败关闭**：扫描版、加密、空白或无法解析的 PDF 不会伪装成成功导入。

## 联网核验是可选证据层

外部检索没有被删除，但已从产品主入口降为按需使用的证据审计：

```text
论文原文陈述 → 可选外部检索 → 信源身份与风险检查 → 支持 / 反证 / 冲突 / 证据不足
```

FastRead 明确区分三种结论：

- **论文身份确认**：说明作者、年份、venue、DOI 或官方链接等身份信息对得上。
- **原文定位成功**：只说明这篇论文确实在某页这样写。
- **实验真实复现**：必须另有执行环境、日志与结果证据；阅读报告和联网检索都不能替代复现。

## 快速开始

### 1. 准备后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### 2. 准备前端

```powershell
cd ..\fastread-frontend
corepack enable
pnpm install
cd ..
```

### 3. 启动 FastRead

```powershell
.\run.bat --no-open
```

| 服务 | 默认地址 |
| --- | --- |
| Web 工作台 | `http://127.0.0.1:3015/` |
| 后端 API | `http://127.0.0.1:8483/api/` |
| 健康检查 | `http://127.0.0.1:8483/api/sys_check` |

Windows 根目录脚本还支持：

```text
run.bat           启动后端与前端
run.bat --status  查看运行状态
run.bat --stop    停止本地进程
run.bat --check   检查本地依赖
```

Docker Compose 是可选部署路径，不是本地开发的前置条件：

```powershell
docker compose up -d --build
```

更细的操作步骤见 [README-usage.md](./README-usage.md)，部署说明见 [DEPLOYMENT.md](./DEPLOYMENT.md)。

## 使用流程

1. 在工作台点击“导入论文”，选择本地 PDF 或粘贴论文 URL。
2. 打开“分页原文”，先确认页数、正文和来源是否正确。
3. 生成“关键问题”报告，检查研究问题、方法、证据与局限。
4. 在“主要过程”和“主要贡献”中逐条核对页码与引文。
5. 写下不超过 300 字的个人总结。
6. 进入“持续追问”，继续围绕当前论文提问并检查回答页码。
7. 只有需要外部支持、反证或信源审计时，再进入可选证据层。

## 项目结构

```text
.
├── backend/               # FastAPI、PDF 解析、阅读报告、问答与证据审计
├── fastread-frontend/     # React 论文阅读工作台
├── fastread-extension/    # 可选的浏览器证据审计入口
├── docs/                  # 产品需求与证据契约
├── readme/                # 工程计划和交接材料
├── task/                  # PRD 与使用指南
├── run.bat                # Windows 本地统一入口
└── docker-compose.yml     # 可选容器部署
```

### 技术栈

| 模块 | 主要技术 |
| --- | --- |
| Web | React 19、TypeScript、Vite、Tailwind CSS、Zustand |
| API | Python、FastAPI、SQLAlchemy、SQLite |
| 扩展 | Vue 3、TypeScript、WebExtension MV3 |
| 部署 | Windows 脚本、Docker Compose、Nginx |

产品与证据约束详见 [docs/FASTREAD_REQUIREMENTS.md](./docs/FASTREAD_REQUIREMENTS.md)。

## 配置

本地配置位于根目录 `.env`；密钥不得写入 Git 跟踪文件。

| 变量 | 用途 | 示例 |
| --- | --- | --- |
| `BACKEND_HOST` | 后端监听地址 | `0.0.0.0` |
| `BACKEND_PORT` | 后端端口 | `8483` |
| `VITE_API_BASE_URL` | 前端 API 地址 | `/api` |
| `NOTE_OUTPUT_DIR` | 本地任务与证据产物目录 | `note_results` |
| `ONLINE_VERIFY_SEARCH_PROVIDER` | 可选证据审计的搜索源 | `brave` |
| `BRAVE_SEARCH_API_KEY` | Brave Search API Key | 仅存本地 |

## 验证

```powershell
# 后端测试
backend\.venv\Scripts\python.exe -m pytest

# 前端生产构建
cd fastread-frontend
corepack pnpm run build

# 扩展生产构建
cd ..\fastread-extension
npm run build
```

浏览器验收使用 Playwright 启动 Microsoft Edge（`channel: "msedge"`）。

## 当前范围

已实现：

- [x] PDF 逐页解析与持久化
- [x] 从论文详情页跟随可用 PDF 元数据
- [x] 关键问题、方法、贡献、实验与局限报告
- [x] 报告引文与分页原文精确匹配
- [x] 300 字个人总结独立保存
- [x] 单篇论文页码感知问答
- [x] 学术身份 Gate 与外部证据层分离

仍在路线图中：

- [ ] 扫描版 PDF 的受控 OCR
- [ ] 论文页内高亮与引用跳转
- [ ] 限定会议语料的论文搜索
- [ ] 从阅读报告生成带引用的演示文稿

## License

[MIT](./LICENSE)
