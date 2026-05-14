# 抖音精选知识管理助手使用说明

更新时间：2026-05-14

## 当前 demo 能做什么

这个仓库已经从原始 BiliNote 收口成“抖音精选知识管理助手”的 demo 版本。

当前可跑通的主流程：

1. 打开 Web 前端。
2. 输入抖音精选视频链接。
3. 后端解析视频信息并下载音频。
4. 转写音频。
5. 调用已配置的大模型生成 Markdown 笔记。
6. 在“我的收藏”里回看笔记。
7. 在笔记页切换为思维导图视图。

当前 demo 重点验证的是：

- 抖音精选链接输入
- AI 知识提取
- AI 总结
- 收藏列表回看
- Markdown/思维导图展示

## 启动方式

推荐使用 demo 端口，避免和旧进程冲突：

- 后端：`http://127.0.0.1:8493`
- 前端：`http://127.0.0.1:3016`

### 启动后端

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

### 启动前端

另开一个终端，在仓库根目录执行：

```powershell
cd BillNote_frontend
$env:VITE_API_BASE_URL="http://127.0.0.1:8493/api"
npm run dev -- --host 127.0.0.1 --port 3016 --strictPort
```

打开：

```text
http://127.0.0.1:3016
```

不要直接打开 `http://127.0.0.1:8493`，那是后端 API 根路径，会返回 `{"detail":"Not Found"}`，这是正常现象。

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
8. 笔记页顶部可切换“思维导图”。

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

- `bcut` 第三方服务异常时，会自动回退到 `fast-whisper`
- `bcut` 返回空转写时，也会自动回退到 `fast-whisper`

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

正常情况下应能看到 `HasCookie = True`。

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

查看已生成知识卡片列表：

```text
http://127.0.0.1:8493/api/tasks
```

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

这种情况下，仅靠音频转写会导致笔记信息量有限。后续需要增强“视频理解/截图 OCR/页面字幕提取”能力。

## 当前未完成事项

还没彻底产品化的部分：

- 收藏夹、标签、备注目前主要是前端本地持久化，后端还没有正式收藏表。
- `/api/tasks` 当前从 `note_results` 文件夹恢复结果，是 demo 级实现。
- 删除接口还没有彻底清理所有结果文件。
- 思维导图仍基于 Markdown 自动转换，后续可加入专门的导图 prompt。
- Cookie 同步体验还偏技术，需要更友好的前端提示。

## 推荐下一步

下一位接手的人建议优先做：

1. 把收藏夹、标签、备注后端持久化。
2. 优化 Cookie 状态提示。
3. 给思维导图加专用生成 prompt。
4. 针对音频信息少的视频，补充字幕抓取或 OCR 路径。
