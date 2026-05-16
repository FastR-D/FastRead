<p align="center">
  <img src="./doc/icon.svg" alt="ReelMind Logo" width="72" height="72" />
</p>

<h1 align="center">ReelMind</h1>

<p align="center">
  <strong>把知识视频变成可复习、可搜索、可追问的 AI 笔记</strong>
</p>

<p align="center">
  把短视频变成可沉淀的知识，支持视频解析、音频转写、AI 总结、Markdown 笔记、思维导图、收藏回看和上下文问答。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License" />
  <img src="https://img.shields.io/badge/frontend-React%2019-61dafb" alt="React" />
  <img src="https://img.shields.io/badge/backend-FastAPI-009688" alt="FastAPI" />
  <img src="https://img.shields.io/badge/extension-Vue%203-42b883" alt="Vue" />
  <img src="https://img.shields.io/badge/AI-OpenAI%20%7C%20DeepSeek%20%7C%20Qwen-ff69b4" alt="AI Providers" />
  <img src="https://img.shields.io/badge/Docker-ready-2496ed" alt="Docker" />
</p>

---

## 目录

- [项目亮点](#项目亮点)
- [界面预览](#界面预览)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [使用流程](#使用流程)
- [配置说明](#配置说明)
- [浏览器扩展](#浏览器扩展)
- [常见问题](#常见问题)
- [项目结构](#项目结构)
- [路线图](#路线图)
- [许可证](#许可证)

## 项目亮点

ReelMind 当前版本已经收口为抖音精选知识视频演示版，重点验证从视频链接到知识资产的完整闭环。

- **一键生成知识笔记**：输入抖音精选视频链接，自动解析视频信息、下载音频、转写内容并生成结构化 Markdown。
- **思维导图视图**：从笔记中提取专用 `## 思维导图` 章节，使用 Markmap 渲染可视化知识结构。
- **收藏与回看**：支持收藏夹、标签和备注，生成记录会持久化到后端，刷新或重启后仍可恢复。
- **AI 上下文问答**：基于当前任务的视频元信息、转写文本和笔记内容进行追问。
- **多模型供应商**：支持 OpenAI 兼容接口、DeepSeek、Qwen 等模型供应商配置。
- **转写兜底策略**：支持 bcut、fast-whisper、Groq、MLX Whisper 等转写方式，并在低质量 ASR 场景下合并视频元信息。
- **浏览器扩展辅助**：扩展提供 Cookie 同步、页面入口、弹窗和侧边栏能力，降低抖音登录态配置成本。

## 界面预览

<p align="center">
  <img src="./doc/image1.png" alt="ReelMind Preview 1" width="860" />
</p>

<p align="center">
  <img src="./doc/image3.png" alt="ReelMind Preview 2" width="860" />
</p>

<p align="center">
  <img src="./doc/image4.png" alt="ReelMind Preview 3" width="860" />
</p>

## 技术栈

| 模块 | 技术 |
| --- | --- |
| Web 前端 | React 19、Vite、TypeScript、Tailwind CSS、Radix UI、Zustand、Markmap |
| 后端服务 | Python、FastAPI、SQLAlchemy、SQLite、Uvicorn |
| 浏览器扩展 | Vue 3、Vite、WebExtension MV3、UnoCSS |
| 桌面端预留 | Tauri 2 |
| AI 与转写 | OpenAI Compatible API、DeepSeek、Qwen、faster-whisper、bcut、Groq |
| 部署 | Docker Compose、Nginx |

## 快速开始

### 方式一：Docker 一键启动

Windows 用户可以直接双击根目录的 `start-demo.bat`。

脚本会自动：

- 检查 Docker Desktop 是否可用
- 创建默认 `.env`
- 启动后端、前端和 Nginx
- 通过健康检查后打开浏览器

默认访问地址：

```text
http://127.0.0.1:3015/
```

也可以在终端中手动启动：

```powershell
docker compose up -d
```

停止服务：

```powershell
docker compose down
```

### 方式二：源码开发启动

准备环境：

- Python 3.11
- Node.js 20+
- FFmpeg
- npm 或 pnpm

复制环境变量：

```powershell
Copy-Item .env.example .env
```

启动后端：

```powershell
cd backend
pip install -r requirements.txt
$env:BACKEND_PORT="8493"
python main.py
```

后端健康检查：

```text
http://127.0.0.1:8493/api/sys_check
```

启动前端：

```powershell
cd BillNote_frontend
npm install
$env:VITE_API_BASE_URL="http://127.0.0.1:8493/api"
npm run dev -- --host 127.0.0.1 --port 3016 --strictPort
```

开发访问地址：

```text
http://127.0.0.1:3016/
```

后端根路径不是页面入口，直接访问 `http://127.0.0.1:8493` 返回 `{"detail":"Not Found"}` 属于正常现象。

## 使用流程

1. 打开 Web 前端。
2. 在「视频链接」中输入抖音精选链接，例如：

```text
https://www.douyin.com/jingxuan?modal_id=7633777410067926322
```

3. 在设置页确认模型供应商和模型已经配置。
4. 可选填写收藏夹、标签和收藏备注。
5. 点击「生成笔记」。
6. 等待任务完成解析、下载、转写和总结。
7. 在「我的收藏」中回看历史笔记。
8. 切换「Markdown / 思维导图 / AI 问答」视图继续复习。

生成结果默认写入：

```text
backend/note_results/
```

常见结果文件：

```text
{task_id}.json
{task_id}.status.json
{task_id}_audio.json
{task_id}_transcript.json
{task_id}_markdown.md
{task_id}_markdown.status.json
```

## 配置说明

主要配置位于根目录 `.env`。

| 变量 | 说明 | 示例 |
| --- | --- | --- |
| `APP_PORT` | Docker/Nginx 对外端口 | `3015` |
| `BACKEND_HOST` | 后端监听地址 | `0.0.0.0` |
| `BACKEND_PORT` | 后端服务端口 | `8483` |
| `VITE_API_BASE_URL` | 前端请求后端 API 地址 | `/api` 或 `http://127.0.0.1:8493/api` |
| `TRANSCRIBER_TYPE` | 转写器类型 | `bcut`、`fast-whisper`、`groq` |
| `WHISPER_MODEL_SIZE` | Whisper 模型大小 | `tiny`、`base`、`small`、`medium` |
| `NOTE_OUTPUT_DIR` | 笔记结果目录 | `note_results` |
| `FFMPEG_BIN_PATH` | FFmpeg 可执行文件路径 | 留空则使用系统 PATH |

推荐开发期使用：

```env
TRANSCRIBER_TYPE=bcut
WHISPER_MODEL_SIZE=tiny
```

首次触发 `fast-whisper tiny` 时会下载模型到：

```text
backend/models/whisper/whisper-tiny
```

## 浏览器扩展

扩展目录位于 `BillNote_extension/`，用于同步抖音 Cookie、提供 popup、设置页和视频页入口。

安装依赖：

```powershell
cd BillNote_extension
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
BillNote_extension/extension/
```

抖音详情接口依赖有效 Cookie。如果视频详情为空、提示需要登录或下载失败，优先检查：

```text
http://127.0.0.1:8493/api/downloader_cookie_status/douyin
```

推荐同步方式：

1. 在浏览器中打开抖音精选并登录。
2. 打开 ReelMind 浏览器扩展。
3. 点击 Cookie 状态块中的「同步 Cookie」。
4. 回到 Web 设置页刷新状态。

## 常见问题

### 页面一直显示后端初始化中

检查前端是否指向了正确后端：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8493/api"
```

修改后需要重启前端服务，并在浏览器中按 `Ctrl + F5` 强制刷新。

### 生成失败并提示第三方服务异常

通常是在线转写服务波动。当前后端会自动尝试回退到 `fast-whisper`。如果仍失败，检查：

- FFmpeg 是否安装并加入 PATH
- `backend/models/whisper/whisper-tiny` 是否下载完整
- 后端日志中的具体异常
- 抖音 Cookie 是否缺失或过期

### 生成成功但笔记内容很少

部分知识视频主要依赖画面文字或字幕，音频里没有完整讲解。当前后端会把标题、文案、描述和话题标签合并进上下文，但画面文字较多的视频仍需要后续增强 OCR 或视频理解能力。

### Docker 服务启动后无法访问

确认端口没有被占用，并查看服务状态：

```powershell
docker compose ps
docker compose logs --tail=80
```

## 项目结构

```text
.
├── backend/               # FastAPI 后端、下载器、转写、AI 总结、数据库
├── BillNote_frontend/     # React Web 前端
├── BillNote_extension/    # 浏览器扩展
├── doc/                   # 文档图片和产品资料
├── nginx/                 # Docker 反向代理配置
├── readme/                # 阶段交接与补充文档
├── docker-compose.yml     # Docker Compose 部署
├── start-demo.bat         # Windows 一键启动脚本
└── README-usage.md        # 当前 demo 的详细使用说明
```

## 路线图

- [x] 抖音精选链接输入与视频元信息解析
- [x] 音频下载、转写和 AI 总结闭环
- [x] 收藏夹、标签、备注与历史回看
- [x] Markdown 笔记和专用思维导图展示
- [x] 基于当前笔记上下文的 AI 问答
- [x] 浏览器扩展 Cookie 同步入口
- [ ] 删除任务时统一清理数据库、结果文件、转写缓存和向量索引
- [ ] 生成失败原因分类与用户可读提示
- [ ] Markdown、图片、PDF、Word 等导出体验完善
- [ ] 针对画面文字知识视频增强截图 OCR 或视频理解
- [ ] 更完整的端到端回归测试

## 相关文档

- [详细使用说明](./README-usage.md)
- [贡献指南](./CONTRIBUTING.md)
- [更新日志](./CHANGELOG.md)
- [发布说明](./RELEASING.md)

## 许可证

本项目基于 [MIT License](./LICENSE) 开源。

抖音下载相关代码参考了 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)。
