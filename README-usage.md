# Reel Mind 使用说明

更新时间：2026-05-15

## 当前 demo 能做什么

这个仓库已经收口成 Reel Mind 的 demo 版本，当前优先面向抖音精选知识视频。

当前可跑通的主流程：

1. 打开 Web 前端。
2. 输入抖音精选视频链接。
3. 后端解析视频信息并下载音频。
4. 转写音频。
5. 调用已配置的大模型生成 Markdown 笔记和专用思维导图章节。
6. 在“我的收藏”里回看笔记，并编辑收藏夹、标签、备注。
7. 刷新或重启后，从后端恢复收藏记录和收藏元数据。
8. 在笔记页切换为思维导图视图，优先渲染 `## 思维导图` 章节。
9. 在笔记页使用基于当前任务索引的 AI 问答。

当前 demo 重点验证的是：

- 抖音精选链接输入
- AI 知识提取
- AI 总结
- 收藏列表回看和收藏元数据后端持久化
- Markdown/专用思维导图展示
- 抖音 Cookie 状态诊断和浏览器扩展同步入口
- 基于笔记/转写/视频元信息的 AI 问答

## 启动方式

推荐优先使用 Docker 启动整套 demo；如果要调试源码，再使用源码端口。

### 方式一：Docker 启动整套服务

在仓库根目录执行：

```powershell
docker compose up -d --build
```

默认访问地址：

```text
http://127.0.0.1:3015/
```

Docker 模式下，后端容器内部监听 `8483`，宿主机通过 Nginx 的 `3015` 端口访问 API：

```text
http://127.0.0.1:3015/api/sys_check
http://127.0.0.1:3015/api/sys_health
```

正常返回：

```json
{"code":0,"msg":"success","data":null}
```

查看服务状态：

```powershell
docker compose ps
```

只看后端日志：

```powershell
docker compose logs --tail=80 backend
```

只重建后端：

```powershell
docker compose up -d --build backend
```

容器内后端健康检查：

```powershell
docker compose exec -T backend curl -sS http://127.0.0.1:8483/api/sys_check
docker compose exec -T backend curl -sS http://127.0.0.1:8483/api/sys_health
```

停止服务：

```powershell
docker compose down
```

如果机器上之前跑过旧容器名，执行一次完整重建会切到当前命名：

```powershell
docker compose down
docker compose up -d --build
```

当前容器名应为：

```text
reel-mind-backend
reel-mind-frontend
reel-mind-nginx
```

### 方式二：源码开发启动

源码开发推荐使用 demo 端口，避免和 Docker 或旧进程冲突：

- 后端：`http://127.0.0.1:8493`
- 前端：`http://127.0.0.1:3016`

#### 启动后端

在仓库根目录执行：

```powershell
cd backend
$env:BACKEND_PORT="8493"
python main.py
```

后端健康检查：

```text
http://127.0.0.1:8493/api/sys_check
```

正常返回：

```json
{"code":0,"msg":"success","data":null}
```

#### 启动前端

另开一个终端，在仓库根目录执行：

```powershell
cd reel-mind-frontend
$env:VITE_API_BASE_URL="http://127.0.0.1:8493/api"
npm run dev -- --host 127.0.0.1 --port 3016 --strictPort
```

打开：

```text
http://127.0.0.1:3016
```

不要直接打开 `http://127.0.0.1:8493`，那是后端 API 根路径，会返回 `{"detail":"Not Found"}`，这是正常现象。

Docker 模式不要访问 `8493`，应访问：

```text
http://127.0.0.1:3015
http://127.0.0.1:3015/api/sys_check
```

## 使用流程

1. 打开 `http://127.0.0.1:3016`。
2. 在左侧“视频链接”输入抖音精选链接，例如：

```text
https://www.douyin.com/jingxuan?modal_id=7633777410067926322
```

3. 确认模型已选择，例如 `deepseek-v4-flash`。
4. 可填写收藏夹、标签、收藏备注。
5. 点击“生成笔记”。
6. 等待状态从解析、下载、转写、总结进入完成。
7. 完成后可在中间栏“我的收藏”里点击卡片回看。
8. 可在“我的收藏”中继续修改收藏夹、标签、备注；修改会防抖同步到后端。
9. 笔记页顶部可切换“思维导图”。
10. 笔记页可切换 AI 问答，基于当前任务内容提问。

## 当前本地配置

当前 demo 使用过的模型配置：

- Provider ID：`deepseek`
- Base URL：`https://api.deepseek.com`
- Model：`deepseek-v4-flash`

如果重建数据库，需要重新在设置页添加 provider 和 model。

当前默认转写配置：

```env
TRANSCRIBER_TYPE=bcut
WHISPER_MODEL_SIZE=tiny
```

后端已加兜底逻辑：

- 抖音精选会优先把视频标题、文案、描述、话题标签当作“平台字幕/元信息”使用
- `bcut` 第三方服务异常时，会自动回退到 `fast-whisper`
- `bcut` 返回空转写时，也会自动回退到 `fast-whisper`
- 如果音频转写很短、明显不是中文、或像示例里误识别成英文数字，后端会把抖音元信息合并进转写内容，避免笔记只基于错误 ASR

首次触发 `fast-whisper tiny` 时，会下载约 72MB 模型到：

```text
backend/models/whisper/whisper-tiny
```

## 抖音 Cookie

抖音视频详情接口依赖有效 Cookie。

如果出现视频详情为空、提示需要登录、或下载失败，优先检查：

1. 浏览器插件是否已同步抖音 Cookie。
2. Cookie 是否过期。
3. 后端是否能读取到 Cookie。

检查接口：

```text
http://127.0.0.1:8493/api/get_downloader_cookie/douyin
```

推荐检查接口：

```text
http://127.0.0.1:8493/api/downloader_cookie_status/douyin
```

如果使用 Docker 启动，对应地址是：

```text
http://127.0.0.1:3015/api/downloader_cookie_status/douyin
```

正常情况下应看到：

```json
{
  "configured": true,
  "valid_looking": true,
  "cookie_count": 2
}
```

`valid_looking = false` 时，通常说明 Cookie 已保存但缺少 `ttwid`、`msToken` 等关键字段，需要重新同步。

### 推荐同步方式

1. 在浏览器中打开抖音精选并登录。
2. 打开 Reel Mind 浏览器扩展 popup。
3. 点击顶部 Cookie 状态块里的“同步 Cookie”。
4. 返回 Web 前端设置页，点击“刷新状态”确认已配置。

Web 设置页不能直接读取浏览器跨域 Cookie，因此只保留手动粘贴作为兜底；真正的一键同步入口在浏览器扩展 popup 和扩展设置页。

## 结果文件位置

生成结果会写入：

```text
backend/note_results/
```

常见文件：

```text
{task_id}.json
{task_id}.status.json
{task_id}_audio.json
{task_id}_transcript.json
{task_id}_markdown.md
{task_id}_markdown.status.json
```

查看任务状态：

```text
http://127.0.0.1:8493/api/task_status/{task_id}
```

Docker 模式：

```text
http://127.0.0.1:3015/api/task_status/{task_id}
```

查看已生成知识卡片列表：

```text
http://127.0.0.1:8493/api/tasks
```

Docker 模式：

```text
http://127.0.0.1:3015/api/tasks
```

`/api/tasks` 当前优先从数据库读取任务记录和收藏元数据，并兼容读取旧的 `note_results` 文件。

## 常见问题

### 页面一直显示“后端正在初始化”

优先检查前端是否指向了正确后端：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8493/api"
```

然后重启前端。

如果浏览器缓存了旧代码，按 `Ctrl + F5` 强制刷新。

### 打开后端地址显示 Not Found

不要打开：

```text
http://127.0.0.1:8493
```

应该打开前端：

```text
http://127.0.0.1:3016
```

后端只通过 `/api/...` 提供接口。

Docker 模式下建议直接打开：

```text
http://127.0.0.1:3015
```

并用下面接口验证后端：

```text
http://127.0.0.1:3015/api/sys_check
```

### 生成失败：第三方服务异常

通常是 `bcut` 在线转写服务波动。当前代码会自动回退到 `fast-whisper`。

如果仍失败，检查：

- `backend/models/whisper/whisper-tiny` 是否下载完整
- 后端日志里的具体异常
- 本机是否能正常读取音频文件

### 生成成功但内容很少

部分抖音精选视频可能是：

- 背景音乐为主
- 画面文字为主
- 字幕/视觉信息承载主要知识
- 音频里没有完整讲解

当前后端已经会优先使用抖音标题、文案、描述、话题标签，并在 ASR 结果低质量时合并这些元信息。若仍然内容很少，通常说明主要知识在画面文字里，后续需要增强“视频理解/截图 OCR/页面字幕提取”能力。

## 当前未完成事项

还没彻底产品化的部分：

- 删除接口按 `task_id` 会清理结果文件和向量索引；按 `video_id` 删除时仍需要补齐对应文件清理。
- `/api/tasks` 已优先读数据库，但仍保留扫描旧 `note_results` 的兼容路径；后续可做一次性导入/迁移。
- 生成失败原因还没有产品化分类展示，常见失败包括 Cookie 缺失/过期、模型供应商未配置、ASR 失败、抖音详情接口失败、LLM 调用失败。
- 思维导图已有专用 prompt 和专用章节渲染，但导出按钮和导出体验仍偏工程化。
- 针对画面文字信息多的视频，仍需增强截图 OCR 或视频理解路径。

## 推荐下一步

下一位接手的人建议优先做：

1. 补齐删除清理：数据库记录、结果 JSON、状态文件、转写缓存、Markdown 缓存、向量索引统一清理。
2. 做生成失败原因分类和用户可读提示。
3. 做一次真实端到端回归：同步 Cookie、生成笔记、编辑收藏元数据、刷新恢复、删除清理。
4. 针对画面文字信息多的视频，补充截图 OCR 或视频理解路径。
