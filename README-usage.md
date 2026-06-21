# ReelMind 使用说明

更新时间：2026-06-21

## 当前主流程

ReelMind 当前优先解决一个问题：

```text
这句话到底有没有可靠联网证据支持？
```

P0 主流程是：

1. 打开 Web 工作台。
2. 粘贴待核实文本，或输入网页 URL。
3. 系统拆分 atomic claims。
4. 多查询、多来源联网检索。
5. 抓取网页/PDF 正文。
6. 判断信源等级、独立性和风险。
7. 抽取正文证据片段。
8. 输出可审计核验报告。

搜索结果摘要只用于召回候选来源，不能单独产生 `supported`。最终判定必须来自已抓取正文证据和规则引擎。

## 启动方式

推荐优先使用 Windows 本地脚本，不再默认要求 Docker。

### 本地脚本

首次运行前需要准备：

- `backend\.venv`
- `reel-mind-frontend\node_modules`

缺少后端虚拟环境时，在仓库根目录执行：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
```

缺少前端依赖时，在仓库根目录执行：

```powershell
cd reel-mind-frontend
corepack enable
pnpm install
cd ..
```

启动：

```powershell
.\run.bat
```

打开：

```text
http://127.0.0.1:3015/
```

本地后端默认监听：

```text
http://127.0.0.1:8483/api/sys_check
http://127.0.0.1:8483/api/sys_health
```

常用脚本参数：

```powershell
.\run.bat --no-open
.\run.bat --status
.\run.bat --stop
.\run.bat --check
```

### 手动开发启动

后端：

```powershell
cd backend
.\.venv\Scripts\python.exe main.py
```

前端：

```powershell
cd reel-mind-frontend
$env:VITE_API_BASE_URL="/api"
pnpm run dev -- --host 0.0.0.0 --port 3015
```

不要直接打开 `http://127.0.0.1:8483`；那是 API 根路径，返回 `{"detail":"Not Found"}` 是正常现象。

### 可选 Docker

Docker 只作为可选部署或高级演示路径：

```powershell
docker compose up -d --build
```

Docker 模式下通过前端/Nginx 访问：

```text
http://127.0.0.1:3015/
http://127.0.0.1:3015/api/sys_check
```

## 联网核实文本

1. 打开 `http://127.0.0.1:3015`。
2. 在左侧输入框粘贴一段文字。
3. 点击 `开始联网核实`。
4. 等待状态经过解析输入、联网检索、抓取信源、评估证据、生成报告。
5. 在报告中查看：
   - 总体判定
   - 每条 atomic claim
   - 正文证据片段
   - 支持/反驳/背景 stance
   - 信源 tier
   - canonical URL、publisher、author、published_at
   - 风险旗标和审计信息

## 联网核实 URL

输入网页 URL 后，系统会先抓取输入源正文，再从正文中拆分主张并核实。

报告顶部会展示输入源审计信息，包括：

- requested URL
- fetched URL
- canonical URL
- redirect chain
- fetch status
- publisher/author/date
- text chars

如果输入源无法抓取，系统应保守返回非 `supported` 结果，并在报告里展示失败状态或风险旗标。

## 重新核实

报告支持两类重跑：

- 整个任务重跑：默认重试失败或未完成的联网阶段。
- 单条主张重跑：只重跑目标 claim，复用其他已完成 claim 的结果。

重跑期间旧报告会保留，界面显示进度条和当前阶段。

## 历史任务

资料库中的任务分为两类：

- 已有核验报告：显示 `支持`、`反证`、`混合`、`证据不足`、`数据空缺` 或 `信源风险`。
- 旧笔记/历史任务：如果没有 `verification_result`，会显示 `未联网核实`，并进入 `需复核`。

打开旧笔记后，联网核实视图会提供 `发起联网核实`，用于把旧笔记升级为可审计核验报告。

## 兼容能力

旧的视频笔记能力仍保留为次级产物：

- 抖音精选链接解析
- 音频转写
- Markdown 笔记
- 思维导图
- 知识卡片
- 基于笔记内容的 AI 问答

这些能力不再是 P0。旧笔记不能默认视为已经联网核实。

## 抖音输入诊断

如果继续使用旧抖音视频笔记流程，可能仍需要 Cookie。

检查接口：

```text
http://127.0.0.1:8483/api/downloader_cookie_status/douyin
```

Docker 模式：

```text
http://127.0.0.1:3015/api/downloader_cookie_status/douyin
```

浏览器扩展当前发布范围是 popup：

- 提交当前页面 URL 或粘贴文本到 `/api/verification_tasks`
- 打开 Web 工作台深链
- 提供抖音输入诊断入口

## 结果位置

结果文件默认写入：

```text
backend/note_results/
```

核验任务会保存：

```text
_verification/<task_id>/claims/<claim_id>.json
```

常用接口：

```text
POST http://127.0.0.1:8483/api/verification_tasks
GET  http://127.0.0.1:8483/api/verification_tasks/{task_id}
POST http://127.0.0.1:8483/api/verification_tasks/{task_id}/rerun
POST http://127.0.0.1:8483/api/verification_tasks/{task_id}/claims/{claim_id}/rerun
GET  http://127.0.0.1:8483/api/verification_tasks
```

兼容旧任务接口：

```text
GET http://127.0.0.1:8483/api/task_status/{task_id}
GET http://127.0.0.1:8483/api/tasks
```

## 常见问题

### 页面一直显示后端初始化

确认前端 API 地址：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8483/api"
```

然后重启前端。浏览器缓存旧代码时按 `Ctrl + F5`。

### 报告没有 supported

这通常是正确的保守行为。以下情况不能输出 `supported`：

- 只有搜索摘要，没有正文证据。
- 抓取失败或正文为空。
- 只有论坛、社交、SEO、榜单、营销页。
- 信源疑似伪权威、重定向异常、canonical 异常。
- 降级搜索不可用。

### 旧笔记显示未联网核实

旧任务没有可审计 `verification_result`。打开任务后点击 `发起联网核实`，系统会尝试基于旧任务内容补充证据报告。

## 下一步重点

1. 继续扩充真实 GEO/language disagreement fixtures。
2. 扩展 prompt injection、SEO farm、fake authority、repost、data void 测试。
3. 处理 standalone `tsc --noEmit` 里的历史前端类型错误。
4. 决定扩展是否激活 sidepanel/content script；如果激活，必须转向进度/证据/选中文本核验。
5. 持续清理旧文档里的 note-first 和 Cookie-first 叙事。
