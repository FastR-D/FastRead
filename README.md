<p align="center">
  <img src="./doc/icon.png" alt="FastRead" width="72" height="72" />
</p>

<h1 align="center">FastRead</h1>

<p align="center">
  <strong>从论文原文出发，把“读过”变成可回到页码核对的理解。</strong>
</p>

<p align="center">
  导入 PDF 或论文 URL，逐页阅读原文，生成关键问题报告，提炼方法与贡献，发现近邻论文，写下个人总结，并围绕同一篇论文持续追问。
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
  近邻论文 / 相关工作
        ↓
     个人总结
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
| 近邻论文 | 按带页码的报告锚点发现并排序相关工作 | 展示重合词、来源和时间，不做真假裁决 |
| 个人总结 | 将用户自己的理解与 AI 报告分开保存 | 可写短摘要，也可展开为完整阅读笔记 |
| 持续追问 | 优先以当前论文分页原文回答 | 实质结论显示页码；无支撑时说明证据不足 |

## 核心能力

- **分页优先**：论文正文按页持久化，阅读、报告和问答共享同一份原文基础。
- **固定问题框架**：报告集中回答研究问题、主要过程、主要贡献、实验依据和局限，减少零散摘要。
- **可追溯引用**：报告证据同时记录起止页码；无法在对应页面匹配的引文不会进入结果。
- **原文约束问答**：围绕单篇论文连续提问，答案尽量附带页码，不用模型常识填补原文空白。
- **个人理解沉淀**：提供可长可短的独立总结，不用 AI 报告替代用户自己的判断。
- **蓝色用户摘录**：页内拖选原文即可保存逐字摘录、批注、页码、偏移和来源哈希；与琥珀色 AI 引用定位明确分色。
- **发现收件箱**：单边读取 FastNews 固定公开 JSONL，并兼容 FastInsight `verify_paper.py` JSON；候选经用户确认后才重新抓取原文。
- **专题证据矩阵**：按问题、方法、实验、局限组织多篇论文的逐字页码证据；用户假设始终独立展示。
- **不可变写作交接**：通过 FastWrite 现有文件创建接口写入唯一证据包目录，失败可重试缺失项或下载 ZIP / Markdown / BibTeX / JSON。
- **失败关闭**：扫描版、加密、空白或无法解析的 PDF 不会伪装成成功导入。

## 近邻论文是一条元数据发现链

近邻检索从已经落到原文页码的研究问题、方法与贡献生成确定性锚点：

```text
报告锚点 → 核心会议 / arXiv / Scholar 元数据 → 去重与相关度排序 → 来源展示
```

FastRead 明确区分三种边界：

- **论文身份确认**：说明作者、年份、venue、DOI 或官方链接等身份信息对得上。
- **原文定位成功**：只说明这篇论文确实在某页这样写。
- **近邻论文发现**：只说明研究问题、方法或贡献相似，不判断主张正确性，也不替代实验复现。

## 快速开始

### Windows 安装包（普通用户推荐）

从 [GitHub Releases](https://github.com/FastR-D/FastRead/releases) 下载同一版本的 Windows `*-setup.exe` 和 `SHA256SUMS-x86_64-pc-windows-msvc.txt`。`setup.exe` 是默认的当前用户安装包，不要求把程序写入系统目录；`.msi` 主要用于管理员或受管环境部署。

```powershell
(Get-FileHash .\FastRead-setup.exe -Algorithm SHA256).Hash
```

将命令输出与 Windows 目标对应的 `SHA256SUMS-*.txt` 条目核对后再运行安装程序。缺少 Microsoft Edge WebView2 Runtime 时，安装程序会联网下载；离线安装机器需要先部署 WebView2。当前自动发布链路尚未接入代码签名证书，因此自建或现阶段发布的安装包可能触发 Windows SmartScreen，面向公众发布前应完成签名和时间戳配置。

升级时直接运行更高版本安装包，Windows 会阻止覆盖安装旧版本。卸载只删除应用和随附后端，默认保留 `%APPDATA%\com.fastread.app` 中的数据库、论文、索引、配置与密钥材料，以及 `%LOCALAPPDATA%\com.fastread.app` 中的 WebView 本地草稿与界面状态；备份或彻底清除方法见 [DEPLOYMENT.md](./DEPLOYMENT.md)。

### 从源码启动（开发者）

#### 1. 准备后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

#### 2. 准备前端

```powershell
cd ..\fastread-frontend
corepack enable
pnpm install
cd ..
```

#### 3. 启动 FastRead

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

Compose 默认只监听 `127.0.0.1:3015`，不直接暴露后端端口；运行数据保存在命名卷 `fastread-data`，重建容器不会丢失数据库、上传文件、笔记与索引。仓库 `.env` 不是 Compose 启动的必需文件。

更细的操作步骤见 [README-usage.md](./README-usage.md)，部署说明见 [DEPLOYMENT.md](./DEPLOYMENT.md)。

## 使用流程

1. 在工作台点击“导入论文”，选择本地 PDF 或粘贴论文 URL。
2. 打开“分页原文”，先确认页数、正文和来源是否正确。
3. 生成“关键问题”报告，检查研究问题、方法、证据与局限。
4. 在“主要过程”和“主要贡献”中逐条核对页码与引文。
5. 在“近邻论文”中查看与研究问题、方法或贡献相近的相关工作及元数据来源。
6. 写下个人总结：可用短摘要概括，也可展开成完整阅读笔记。
7. 进入“持续追问”，继续围绕当前论文提问并检查回答页码。
8. 在专题知识库中管理组内论文、原文摘录与研究整理，并按需交接到 FastWrite。

## 项目结构

```text
.
├── backend/               # FastAPI、PDF 解析、阅读报告、相关工作与问答
├── fastread-frontend/     # React 论文阅读工作台
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
| 部署 | Windows 脚本、Docker Compose、Nginx |

产品与证据约束详见 [docs/FASTREAD_REQUIREMENTS.md](./docs/FASTREAD_REQUIREMENTS.md)。

## 配置

本地配置位于根目录 `.env`；密钥不得写入 Git 跟踪文件。

| 变量 | 用途 | 示例 |
| --- | --- | --- |
| `BACKEND_HOST` | 本地后端监听地址 | `127.0.0.1` |
| `BACKEND_PORT` | 后端端口 | `8483` |
| `VITE_API_BASE_URL` | 前端 API 地址 | `/api` |
| `PAPER_OUTPUT_DIR` | 论文正文与派生产物目录 | `paper_results` |
| `FASTNEWS_ENABLED` | 是否启用固定 FastNews 公开目录适配器 | `true` |
| `FASTWRITE_BASE_URL` | FastWrite 精确 origin | `http://127.0.0.1:3003` |
| `FASTWRITE_ALLOWED_ORIGINS` | 显式允许的远程 FastWrite origin，逗号分隔 | 空（仅 loopback） |
| `INTEGRATION_DATA_DIR` | FastNews 缓存、专题综合和交接包目录 | `data/integrations` |
| `PAPER_SEARCH_DEADLINE` | 近邻论文冷检索总时限（秒） | `8` |

## 验证

```powershell
# 后端测试
backend\.venv\Scripts\python.exe -m pytest

# 前端生产构建
cd fastread-frontend
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run test
corepack pnpm run build

```

浏览器验收使用 Playwright 启动 Microsoft Edge（`channel: "msedge"`）。

## 当前范围

已实现：

- [x] PDF 逐页解析与持久化
- [x] 从论文详情页跟随可用 PDF 元数据
- [x] 关键问题、方法、贡献、实验与局限报告
- [x] 报告引文与分页原文精确匹配
- [x] 个人总结可长可短并独立保存
- [x] 单篇论文页码感知问答
- [x] 学术身份 Gate 与近邻论文发现分离
- [x] 论文页内用户摘录、批注、检索、重载恢复和精确回跳
- [x] FastNews/FastInsight 候选收件箱、固定顺序去重和离线缓存标识
- [x] 专题证据矩阵、跨论文共同报告门槛和 Idea 可行性边界
- [x] FastWrite 不可变证据包、部分写入重试、幂等回执和离线下载

仍在路线图中：

- [ ] 扫描版 PDF 的受控 OCR
- [x] 论文页内高亮与引用跳转
- [x] 限定会议语料的论文发现目录
- [x] 带页码锚点的近邻论文视图与提供方状态
- [ ] 从阅读报告生成带引用的演示文稿

## License

[MIT](./LICENSE)
