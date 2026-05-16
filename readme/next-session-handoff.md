# ReelMind 独立改造项目交接文档

更新时间：2026-05-15

## 0. 2026-05-15 最新进展

本次已在 MVP 主线上继续完成以下内容：

### 0.0 2026-05-16 Docker 启动与后端验证补充

当前推荐优先用 Docker 启动整套服务：

```powershell
docker compose up -d --build
```

默认访问入口：

```text
Web:      http://127.0.0.1:3015/
API:      http://127.0.0.1:3015/api/...
健康检查: http://127.0.0.1:3015/api/sys_check
```

只重建后端：

```powershell
docker compose up -d --build backend
```

查看状态和日志：

```powershell
docker compose ps
docker compose logs --tail=80 backend
```

容器内验证：

```powershell
docker compose exec -T backend curl -sS http://127.0.0.1:8483/api/sys_check
docker compose exec -T backend curl -sS http://127.0.0.1:8483/api/sys_health
```

已验证返回：

```json
{"code":0,"msg":"success","data":null}
```

当前 compose 命名应为：

```text
reel-mind-backend
reel-mind-frontend
reel-mind-nginx
```

如果本机残留旧容器名，执行：

```powershell
docker compose down
docker compose up -d --build
```

### 0.1 收藏管理后端持久化

已完成：

- `video_tasks` 表新增收藏与视频元数据字段：
  - `video_url`
  - `title`
  - `cover_url`
  - `collection_folder`
  - `collection_tags`
  - `collection_note`
  - `updated_at`
- `init_db` 增加轻量迁移逻辑，旧 SQLite 表启动时会自动补缺失列。
- `/api/generate_note` 提交任务时会先写入任务记录和收藏元数据。
- `/api/tasks` 优先从数据库恢复任务和收藏元数据，同时兼容旧 `note_results` 文件。
- Web 端“我的收藏”中编辑收藏夹、标签、备注后，会 500ms 防抖同步到后端。

关键文件：

- `backend/app/db/models/video_tasks.py`
- `backend/app/db/init_db.py`
- `backend/app/db/video_task_dao.py`
- `backend/app/routers/note.py`
- `BillNote_frontend/src/store/taskStore/index.ts`
- `BillNote_frontend/src/services/note.ts`

### 0.2 Cookie 状态诊断与前端同步入口

已完成：

- 后端新增 `GET /api/downloader_cookie_status/{platform}`。
- Cookie 保存时记录 `updated_at`。
- 状态接口返回：
  - `configured`
  - `valid_looking`
  - `cookie_count`
  - `length`
  - `missing_keys`
  - `updated_at`
- 扩展 popup 顶部新增 Cookie 状态块：
  - 已同步 / 需重新同步 / 未同步
  - 一键“同步 Cookie”
  - “打开抖音精选”登录入口
- 扩展设置页继续保留 Cookie 同步与手动保存。
- Web 下载器设置页明确说明 Web 端无法直接读取跨域 Cookie，推荐使用扩展 popup 同步，并保留手动粘贴兜底。

关键文件：

- `backend/app/services/cookie_manager.py`
- `backend/app/routers/config.py`
- `BillNote_extension/src/popup/Popup.vue`
- `BillNote_extension/src/options/pages/Downloader.vue`
- `BillNote_extension/src/logic/api.ts`
- `BillNote_extension/src/logic/cookies.ts`
- `BillNote_frontend/src/components/Form/DownloaderForm/Form.tsx`
- `BillNote_frontend/src/services/downloader.ts`

### 0.3 思维导图专用生成和渲染

已完成：

- 后端 prompt 增加 `mindmap` 输出格式。
- 默认输出格式包含：
  - `toc`
  - `summary`
  - `mindmap`
- LLM 会在笔记末尾生成 `## 思维导图` 专用章节。
- Web 和扩展的 Markmap 渲染会优先提取 `## 思维导图` 到下一个 `##` 之间的内容。
- 旧笔记没有该章节时，仍回退渲染整篇 Markdown。

关键文件：

- `backend/app/gpt/prompt_builder.py`
- `BillNote_frontend/src/constant/note.ts`
- `BillNote_frontend/src/pages/HomePage/components/NoteForm.tsx`
- `BillNote_frontend/src/pages/HomePage/components/MarkmapComponent.tsx`
- `BillNote_frontend/src/utils/mindmap.ts`
- `BillNote_extension/src/logic/types.ts`
- `BillNote_extension/src/logic/constants.ts`
- `BillNote_extension/src/logic/storage.ts`
- `BillNote_extension/src/logic/mindmap.ts`
- `BillNote_extension/src/components/MindMap.vue`

### 0.4 删除接口的当前状态

已完成：

- `/api/delete_task` 按 `task_id` 删除时会清理：
  - 数据库任务记录
  - `note_results/{task_id}*` 结果文件
  - Chroma 向量索引

仍待补齐：

- 按 `video_id` 删除时，目前只删数据库记录，还没有逐个清理相关结果文件和向量索引。

### 0.5 当前验证结果

已通过：

```powershell
cd BillNote_extension
npm run typecheck
```

```powershell
cd BillNote_frontend
npm run build
```

```powershell
cd backend
python -m py_compile app\db\video_task_dao.py app\routers\note.py
```

```powershell
git diff --check
```

说明：

- Web 构建需要在沙盒外/提权环境运行，否则 Vite/esbuild 可能因为目录权限报 `Access is denied`。
- 构建仍有既有警告：`lottie-web` 使用 `eval`、部分 chunk 超过 500KB；当前不影响构建通过。

### 0.6 当前建议下一步

优先继续：

1. 补齐删除清理：按 `video_id` 删除时同步清理结果文件、缓存文件、向量索引。
2. 做生成失败原因分类展示：Cookie、模型供应商、ASR、抖音详情接口、LLM 调用。
3. 做真实端到端回归：同步 Cookie、生成笔记、查看导图、编辑收藏元数据、刷新恢复、删除清理。

---

## 1. 当前目标

本仓库不再按原始工程的“通用 AI 视频笔记工具”方向继续推进。

当前改造目标已经收敛为：

- 产品名：`ReelMind`
- 核心场景：`抖音精选知识视频`
- 当前 MVP 只做 4 件事：
  - 视频收藏管理
  - AI 知识提取
  - AI 知识总结
  - 思维导图生成

明确暂不做：

- 讲解动画
- 学习计划
- 知识关联推荐
- 知识图谱
- 多平台统一支持
- 视频下载 / 离线播放
- 移动端原生 App
- 社交功能

PRD 参考文件在：

- `C:\Users\Lenovo\Downloads\PRD.md`

## 2. 仓库现状

当前工作目录：

- `C:\Users\Lenovo\Desktop\schoolwork\bilinote`

源码状态：

- 已经拉取官方源码并解压到当前目录
- 本地已经初始化 git 仓库，但还没有远程仓库
- 当前仓库里大部分文件对 git 来说仍是未跟踪状态，这是正常现象，不代表改坏

运行方式：

- 已整理成 `docker compose` 可运行结构
- 根目录已有 `.env`
- `docker-compose.yml` 已使用 `mirror.gcr.io` 基础镜像，APT/PIP 默认回退到官方源

关键运行配置：

- 对外访问端口：`3015`
- 后端端口：`8483`
- `.env` 中当前默认转写仍是：
  - `TRANSCRIBER_TYPE=fast-whisper`
  - `WHISPER_MODEL_SIZE=tiny`

注意：

- 这和前端首启引导里推荐的 `bcut` 不一致
- 这是一个后续要统一的点

## 3. 已完成的改造

本轮只做了“第一步：产品骨架收口”，即只改用户看得到的品牌、文案、默认建议，不改底层多平台架构。

### 3.1 品牌与产品表述已切换

已收口到以下表述：

- 正式名称：`ReelMind`
- Slogan：`把短视频变成可沉淀的知识`

已修改的关键文件：

- `backend/app/__init__.py`
- `BillNote_frontend/index.html`
- `BillNote_frontend/src/layouts/RootLayout.tsx`
- `BillNote_frontend/src/layouts/HomeLayout.tsx`
- `BillNote_frontend/src/layouts/SettingLayout.tsx`
- `BillNote_frontend/src/pages/SettingPage/about.tsx`

### 3.2 首启引导已改为中文模型优先

已改内容：

- 默认供应商从 `OpenAI` 改为 `Qwen`
- 默认 Base URL 改为阿里百炼 OpenAI 兼容地址
- 默认模型改为 `qwen-plus`
- 引导文案改成优先使用中文模型供应商
- 转写建议改为中文场景优先
- 首选转写引擎改为 `bcut`

修改文件：

- `BillNote_frontend/src/pages/Onboarding/index.tsx`

### 3.3 Web 端首页默认方向已收口到抖音精选

已改内容：

- 首页空状态文案改为“当前优先整理抖音精选知识视频”
- 表单默认平台从 `bilibili` 改为 `douyin`
- 视频链接输入提示改为“请输入抖音精选视频链接”

修改文件：

- `BillNote_frontend/src/pages/HomePage/components/MarkdownViewer.tsx`
- `BillNote_frontend/src/pages/HomePage/components/NoteForm.tsx`

### 3.4 思维导图与关于页已对齐新产品定位

已改内容：

- 关于页不再宣传原始多平台开源产品
- 说明当前产品边界、当前 MVP、非 MVP 范围
- 思维导图导出标题改为新产品名

修改文件：

- `BillNote_frontend/src/pages/SettingPage/about.tsx`
- `BillNote_frontend/src/pages/HomePage/components/MarkmapComponent.tsx`

### 3.5 浏览器插件文案已同步

已改内容：

- 扩展名称改为 `ReelMind`
- popup、sidepanel、options、悬浮按钮、右键菜单文案已切换
- 插件设置页加入“优先中文模型”的说明

修改文件：

- `BillNote_extension/package.json`
- `BillNote_extension/src/contentScripts/views/App.vue`
- `BillNote_extension/src/popup/Popup.vue`
- `BillNote_extension/src/sidepanel/Sidepanel.vue`
- `BillNote_extension/src/options/Options.vue`
- `BillNote_extension/src/options/pages/Providers.vue`
- `BillNote_extension/src/options/pages/General.vue`
- `BillNote_extension/src/background/main.ts`

## 4. 当前没有处理的部分

以下内容这次故意没动：

- 后端下载器
- URL 校验器
- 平台识别逻辑
- 数据模型
- 数据库存储结构
- 原有多平台分支
- 浏览器插件真实平台接入逻辑

原因：

- 当前阶段先做低风险收口
- 先让产品“看起来已经是新项目”
- 再逐步收缩底层实现

## 5. 当前遗留问题

这些问题下一轮需要优先继续：

### 5.1 产品文案和底层能力还不完全一致

虽然界面已经收口到抖音精选，但代码底层仍然大量保留：

- `bilibili`
- `youtube`
- `kuaishou`
- 本地视频

这意味着：

- 当前产品叙事已经改变
- 但技术实现还没有真正缩成“抖音精选单场景”

### 5.2 默认转写配置不一致

前端引导中推荐：

- `bcut`

根目录 `.env` 当前默认仍是：

- `fast-whisper`

后续需要决定：

1. 是把 `.env` 默认改成在线中文转写
2. 还是保留本地转写为系统默认，只把前端引导当作建议

建议下一轮统一成一个口径。

### 5.3 仍有大量旧品牌和旧平台引用存在

这次只改了用户可见入口，仓库里仍然会有很多旧品牌或旧平台关键词：

- 旧品牌名
- `BillNote`
- `bilibili`
- `YouTube`
- `多平台`

其中很多在：

- 注释
- 下载器
- 平台识别
- 扩展逻辑
- 常量定义

这些不能用全局替换硬改，必须按模块收缩。

### 5.4 本地验证环境不完整（历史记录）

以下是 2026-05-15 当轮的历史状态；2026-05-16 已补充 Docker 验证，见本文档 0.0。

本轮无法在当前 shell 中完成完整验证，原因是：

- `docker` 命令当前不可用
- `pnpm` 命令当前不可用
- `BillNote_frontend` 和 `BillNote_extension` 下没有本地 `node_modules`

因此本轮只做了：

- 静态修改
- 字符串回查
- 人工检查几个关键文件结构

没有完成：

- 前端构建
- 插件构建
- docker 重新构建验证

## 6. 建议的下一步执行顺序

下一次对话建议直接按这个顺序推进：

### 第 2 步：收缩流程层，只保留抖音精选主路径

优先从“暴露给用户的流程”开始，而不是先改最深处的下载器。

建议顺序：

1. 收缩 Web 端平台选择
2. 收缩插件支持提示
3. 收缩扩展平台识别入口
4. 收缩后端默认请求参数

具体建议：

#### 2.1 前端表单层

先处理：

- `BillNote_frontend/src/constant/note.ts`
- `BillNote_frontend/src/pages/HomePage/components/NoteForm.tsx`

目标：

- 平台下拉先只保留 `douyin`
- 去掉与当前产品无关的显式平台提示
- 保留内部兼容值，但不要继续暴露给用户

#### 2.2 插件入口层

先处理：

- `BillNote_extension/src/logic/platform.ts`
- `BillNote_extension/src/popup/Popup.vue`
- `BillNote_extension/src/background/main.ts`
- `BillNote_extension/src/contentScripts/views/App.vue`

目标：

- 把产品主入口收缩为抖音
- 兼容层是否保留，按风险再判断
- 右键菜单和悬浮按钮只强调抖音精选流程

#### 2.3 后端请求入口层

重点看：

- 路由接收参数
- 平台默认值
- 平台校验入口

此阶段先不要急着删下载器实现，先看调用链，找到真正的主路径。

## 7. 模型策略结论

甲方要求中国模型，这件事已经在当前设计里确定。

建议默认策略：

- 默认主模型：`qwen3.6-plus`
- 超长上下文：`qwen-long`
- 低成本批处理：`deepseek-v4-flash`
- 高质量总结/成稿：`deepseek-v4-pro`

原因：

- 中文表达质量更稳
- 更适合长摘要、知识整理、结构化输出
- 现有代码路径更容易接 OpenAI 兼容接口

## 8. 下一次对话建议直接引用的上下文

下一次可以直接告诉模型：

1. 仓库根目录是 `C:\Users\Lenovo\Desktop\schoolwork\bilinote`
2. PRD 在 `C:\Users\Lenovo\Downloads\PRD.md`
3. 当前目标产品是“ReelMind”
4. 第一步“产品骨架收口”已经完成
5. 下一步要做的是“收缩流程层，只保留抖音精选主路径”
6. 不要先做大规模后端重构
7. 优先处理前端表单、插件入口、平台识别与默认配置

## 9. 本文档用途

这个文档就是给下一次上下文接续用的。

下一轮优先读取：

- `doc/next-session-handoff.md`
- `C:\Users\Lenovo\Downloads\PRD.md`
