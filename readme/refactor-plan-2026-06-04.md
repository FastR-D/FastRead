# Reel Mind 项目重构方案

生成日期：2026-06-04

本方案基于对根目录、`backend/`、`reel-mind-frontend/`、`reel-mind-extension/`、Docker/CI/测试/文档的只读探测，以及一次本地验证。目标不是做“最小可用改动”，而是把项目从当前 demo/迭代堆叠状态，重构成边界清晰、可测试、可部署、可长期扩展的工程结构。

## 执行状态：P0 已收口（2026-06-04）

本轮按方案 A 收缩扩展范围为 Cookie Sync MVP，先保证真实产物可构建、可类型检查；完整 background/content/options/sidepanel 草稿保留在源码中，后续用 `reel-mind-extension/tsconfig.full.json` 暴露并修复缺失契约。

已完成的 P0 项：

- 根目录启动入口收缩为唯一 `run.bat`，旧 Docker/状态/演示 `.bat` 入口已删除；README 和使用文档默认本地启动，Docker 下沉为可选。
- 前端入口文件收缩，删除未引用备用样式入口；修复 `modelStore` 响应解包错位、健康检查 `/api/api`、后端检查全局 toast、任务轮询网络抖动误标失败。
- 后端修复 `ResponseWrapper` HTTP status、上传随机文件名/扩展名/大小限制、图片代理协议/内网地址/内容类型/响应大小限制，并把 provider/model/config/upload 等敏感接口限制为本地访问。
- Docker 可选路径修复 `nginx/default.conf` 写死 `backend:8483`：compose 现在通过 nginx template 注入 `BACKEND_PORT`，并给 `BACKEND_PORT` / `APP_PORT` 提供默认值。
- 扩展统一到 npm，新增 Cookie Sync MVP typecheck 范围；`npm run typecheck` 和 `npm run build` 均通过。仓库根 `.npmrc` 默认使用 `https://registry.npmmirror.com`。

本轮验证：

- `backend\.venv\Scripts\python.exe -m pytest`：82 passed。
- `reel-mind-frontend`：`npm run build` 通过，仍保留既有大 chunk / lottie eval 警告，归入 P5 性能门禁。
- `reel-mind-extension`：`npm run typecheck` 通过；`npm run build` 通过。
- `docker compose config` 通过，已确认 nginx template 和端口默认值可展开。

## 执行状态：P1/P2 继续推进（2026-06-17）

本轮继续按“后端由 Codex 负责、GLM 主要用于前端视觉/实现辅助且必须受监督”的协作方式推进。`glm-frontend-agent` 已切到 opencode 的 `glm-frontend` agent，可在明确分配任务时编辑前端文件；`external_directory` 仍保持 ask，避免越界修改用户目录。

已完成的 P1/P2 项：

- 后端任务契约收敛：新增 `TaskSnapshot` DTO；`/tasks` 和 `/task_status/{task_id}` 统一由 `NoteTaskService` 构造稳定 payload，兼容旧字段并补齐 `updatedAt`、`transcript`、`result`。
- 后端删除任务收敛：`NoteArtifactRepository.delete_task_files()` 改为只清理已知任务产物路径，不再用 `task_id*` glob，避免误删同前缀任务。
- 后端配置/路径集中化：新增 `backend/app/core/settings.py`，统一加载根 `.env` 与 `backend/.env`，并把 `static`、`uploads`、`note_results`、`data`、导出目录、`vector_db`、SQLite、ffmpeg runtime、cookie/transcriber 配置路径收口到 backend 根下的绝对路径。
- 后端 cwd 风险收敛：`main.py`、`note.py`、`db/engine.py`、`sqlite_client.py`、`cookie_manager.py`、`transcriber_config_manager.py`、`post_process_service.py`、`video_helper.py`、`Downloader`、`UniversalGPT`、`VectorStoreManager`、`ExportUtils`、`path_helper`、`ffmpeg_helper` 已接入 settings。
- 前端任务契约归一化：`services/note.ts` 新增 `normalizeTaskSnapshot`，`get_task_status` 和 `list_generated_tasks` 返回 typed snapshot；统一 `audio_meta/audioMeta`，保留 `transcript`，兼容秒级时间戳和 ISO 时间。
- 前端轮询/store 收敛：`useTaskPolling` 使用 normalized snapshot，网络失败保留 retry/backoff，不再把单次异常标为失败；`taskStore` 不再无条件忽略重复 `SUCCESS` 快照，历史任务恢复时保留 transcript/audioMeta/insights。
- 前端工作区拆分继续推进：`MarkdownViewer` 已抽出 `WorkspaceStatusView` 和 `TaskFailureView`，并收窄平台提示到当前支持的 B 站、抖音精选、快手。

本轮验证：

- `backend\.venv\Scripts\python.exe -m pytest --basetemp .tmp\pytest backend\tests`：85 passed。
- `reel-mind-frontend`：`npm run build` 通过，仍保留既有 `lottie-web` eval 和大 chunk 警告。
- `pw-edge.ps1` 全局 wrapper 已固定本地 Playwright CLI，不再依赖临时 `npx`；用户级 npm cache 已固定到 `C:\Users\Lenovo\.codex\npm-cache`。

## 执行状态：P1/P3 继续推进（2026-06-18）

本轮继续采用 Codex 总控、DeepSeek/GLM 窄任务执行、Codex 复核收口的方式推进。DeepSeek 负责后端任务生命周期小步重构，GLM 负责前端工作区组件拆分；两者产物均由 Codex 复核后做了小范围修正和验证。

已完成的 P1/P3 项：

- 后端向量索引生命周期接入可测试路径：`NoteTaskService` 新增 `vector_store_factory` 注入点，默认仍懒加载 `VectorStoreManager`；`index_task()` 与 `delete_task_artifacts()` 继续吞掉向量操作异常，不影响笔记生成和任务删除主流程。
- 后端删除任务测试补齐：`backend/tests/test_note_task_service.py` 新增覆盖已知任务产物清理、`delete_index(task_id)` 调用、向量删除失败不阻断删除流程的用例。
- 前端工作区拆分继续推进：`MarkdownViewer` 已抽出 `MarkdownDocument`，Markdown 渲染、代码高亮复制、图片缩放、视频信息 banner、来源链接剥离、图片 base URL 修正都集中到新组件中，`MarkdownViewer` 只保留版本选择状态、面板状态和工作区编排。

本轮验证：

- `backend\.venv\Scripts\python.exe -m pytest --basetemp .tmp\pytest backend\tests`：87 passed。
- `reel-mind-frontend`：`npm run build` 通过，仍保留既有 `lottie-web` eval 和大 chunk 警告，后续继续归入 P5 性能门禁。

## 执行状态：扩展完整源码契约补齐（2026-06-19）

本轮避开后端 P2/P3、前端 workspace、工程化/文档门禁三个已分派给其他 Codex worker 的方向，单独推进浏览器扩展的完整源码类型契约。默认产物仍保持 Cookie Sync MVP，不把 background/content/options/sidepanel 接入 manifest/build 产物。

已完成项：

- 扩展 `logic/types.ts` 补齐完整扩展源码需要的共享类型：`Settings` 高级生成配置、`TaskRecord`/`TaskStatus`/`TaskSnapshot`、provider/model、转写配置、部署状态等。
- 扩展 `logic/constants.ts` 补齐完整设置默认值、任务存储 key 和任务历史上限。
- 扩展 `logic/storage.ts` 新增任务历史 storage 与 `upsertTask()`，供 sidepanel/background 共享任务状态。
- 扩展 `logic/api.ts` 补齐 options/sidepanel/chat 所需的后端薄封装：provider/model 管理、转写配置、部署监控、任务状态、聊天索引/问答、Markdown 图片地址处理。
- 修正 `Downloader.vue` 的 Cookie MVP 平台类型边界；修正 `ChatPanel.vue` 对后端 `disabled` chat index 状态的类型接收。

本轮验证：

- `reel-mind-extension`：`npx vue-tsc --noEmit --project tsconfig.full.json` 通过，完整扩展源码当前已可类型检查。
- `reel-mind-extension`：`npm run typecheck` 通过，默认 Cookie Sync MVP 类型检查未回退。
- `reel-mind-extension`：`npm run build` 通过，默认 popup-only 产物仍可构建。

## 0. 当前结论

Reel Mind 已经有完整产品闭环：视频链接 -> 下载/字幕/转写 -> LLM 笔记 -> Markdown/思维导图/知识卡片/联网核验 -> 历史收藏/问答。代码并非从零开始的原型，后端也已经拆出了 `MediaService`、`TranscriptService`、`SummaryService`、`PostProcessService`、`NoteArtifactRepository` 等模块。

真正的问题不是“功能不够”，而是边界和契约不够稳定：

- 后端任务事实来源同时存在 SQLite 和 `note_results/*.json`，状态、结果、元数据、索引之间职责交叉。
- 前端把任务历史、当前任务、服务端 DTO、本地 UI 状态、toast、副作用混在 Zustand store 和大组件里。
- 浏览器扩展源码包含 popup、options、background、content script、sidepanel 的完整野心，但实际 manifest/build 只接入 popup，其他功能处于“源码存在但产物不可用”的状态。
- Docker、README、run.bat、CI、扩展说明存在多套端口、包管理器、构建入口和文档口径。
- 测试主要覆盖后端服务层，缺少 PR 质量门禁、前端/扩展真实构建门禁、API 合约测试和端到端回归。

本地验证结果：

- 后端测试：设置 `TMP/TEMP` 到工作区后，`backend\.venv\Scripts\python.exe -m pytest` 通过，`74 passed in 2.69s`。
- 前端构建：`npm run build` 通过，但出现大 chunk 警告，主要包包括 `markmap`、`markdown`、主 `index`、`Model` 等，最大 chunk 超过 3 MB。
- 扩展验证：`npm run typecheck` / `npm run build` 失败，当前 npm 环境找不到 `typescript`、`cross-env`；同时源码层面也存在未纳入 tsconfig 和 build 的 background/content/options/sidepanel 断裂问题。

## 1. 后端重构方案

### 1.1 主要问题

后端入口在 `backend/main.py`，路由通过 `backend/app/__init__.py` 统一挂 `/api`。核心生成链路是：

`backend/app/routers/note.py` -> `NoteTaskService` -> `NoteGenerator` -> `MediaService` / `TranscriptService` / `SummaryService` / `PostProcessService` -> `NoteArtifactRepository` + SQLite DAO。

需要优先处理的问题：

- 路由层存在全局服务实例和内存状态，例如 `NOTE_TASKS`、`cookie_manager`、`transcriber_config_manager`、`_downloading`、`_index_status`。这会影响测试隔离、多进程部署和重启恢复。
- `ResponseWrapper.error()` 默认仍是 HTTP 200，HTTP 语义和业务 code 混在一起。
- DAO 使用 `db = next(get_db())` 手动 session，事务边界无法组合，也不便于测试注入。
- `Provider.id` 与 `Model.provider_id` 类型不一致，模型层缺少明确外键/唯一约束。
- 任务状态、结果文件、数据库元数据双写。`NoteTaskService.list_tasks()` 需要合并 DB 和文件，失败中断时容易出现半状态。
- `/upload` 使用原始 `file.filename` 拼路径，`/image_proxy?url=` 可代理任意 URL，存在路径穿越和 SSRF 风险。
- `task_serial_executor` 名称表示串行，实际是 `ConcurrentTaskExecutor`，后台任务里再提交线程池并同步等待，语义混乱。
- `chat_service.py` 同时负责检索、上下文构造、prompt、工具调用、LLM 调用，后续难测。

### 1.2 目标架构

建议把后端拆成以下稳定边界：

```text
routers/                 只处理 HTTP DTO、Depends、HTTP status
application/             用例层：GenerateNoteTask、DeleteTask、VerifyTask、AskChat
domain/                  Task、Artifact、Provider、Model、Transcript、Verification 等领域模型
repositories/            DB repository + artifact repository，统一接口
workers/                 任务队列/执行器/状态推进
integrations/            downloader、transcriber、LLM、search、vector store
core/settings.py         全局配置、路径、端口、安全策略
```

短期不必一次搬完目录，但新代码应按这个边界组织。

### 1.3 分阶段执行

P0：稳 API 和安全底线

- 为 `ResponseWrapper` 增加可选 HTTP status，不破坏 `{code,msg,data}`，但错误接口返回合适的 4xx/5xx。
- `/upload` 改为随机文件名或安全文件名，限制扩展名和大小。
- `/image_proxy` 限制允许域名，至少只允许 `http/https` 且拒绝内网地址。
- 把 provider、cookie、download、upload 类敏感接口标记为“仅本地可用”或引入本地 token。
- 修正 `nginx/default.conf` 写死 `backend:8483` 的问题，让它跟 `BACKEND_PORT` 或 compose 配置一致。

P1：任务契约收敛

- [x] 定义统一 `TaskSnapshot` DTO：`id/status/message/error/result/collection/audioMeta/createdAt/updatedAt`。
- DB 存任务状态和轻量元数据；`note_results` 只存大体积结果、转写、音频缓存、Markdown。
- [x] `get_task_status`、`list_tasks` 都从同一服务返回 `TaskSnapshot`，文件历史兼容逻辑作为迁移层保留一段时间。
- [x] 删除任务时统一清理 DB、结果文件、转写缓存、音频缓存、Markdown 缓存；向量索引删除已接入同一生命周期并补齐测试。

P2：数据层和配置层重构

- [x] 新增 `app/core/settings.py`，集中 `.env`、路径、端口、输出目录、运行缓存目录；搜索配置和模型缓存目录仍需继续收口。
- [x] `CookieConfigManager`、`TranscriberConfigManager` 接收显式路径，不再隐式依赖 cwd。
- DAO 改为 repository + session 注入；路由通过 FastAPI `Depends` 获取 service。
- 统一 `Provider.id` / `Model.provider_id` 类型，补外键、唯一约束和迁移策略。

P3：生成流水线可测试化

- 把 `NoteGenerator.generate()` 变成明确步骤对象或用例：parse -> subtitle/transcript -> media -> summary -> postprocess -> insights -> persist。
- 执行器改名并明确行为，例如 `TaskExecutor`；如果继续并发，暴露队列状态、取消和最大并发。
- `TranscriptService` 的转写器缓存按 `(type, model_size, device)` 区分，避免用户修改模型后仍复用旧实例。

P4：Chat / Verification 拆分

- `chat_service.py` 拆为 `retriever.py`、`context_builder.py`、`llm_chat_runner.py`、`tool_loop.py`。
- Chroma 向量检索和关键词 fallback 使用同一 `Retriever` 接口。
- 联网核验继续拆 `query_builder/search_orchestrator/verdict/ai_judge`，保留单元测试。

## 2. 前端重构方案

### 2.1 主要问题

前端入口是 `reel-mind-frontend/src/main.tsx` 和 `App.tsx`。当前结构能构建，但维护风险集中在：

- `taskStore` 同时持有任务列表、当前任务、本地持久化、API 调用、toast、DTO 转换、收藏同步。
- `MarkdownViewer.tsx` 同时负责加载/失败状态、Markdown 渲染、版本选择、复制下载、转写、聊天、思维导图、知识卡片。
- `HomeLayout.tsx` 通过 `window.dispatchEvent('reelmind:workspace-command')` 控制工作区，形成隐式跨组件命令流。
- `request.ts` 已解包后端 `data`，但 `modelStore.addNewModel` 仍判断 `res.code === 0`，协议错位。
- `BackendHealthIndicator` 用 `VITE_API_BASE_URL + '/api/sys_health'`，当 env 已经是 `.../api` 时会拼出 `/api/api/sys_health`。
- `useCheckBackend` 用全局 request 做健康检查，会触发全局 toast，并且无限等待逻辑没有取消控制。
- 轮询异常会把任务直接置为 `FAILED`，对网络抖动过于激进。
- UI 系统混用 shadcn/Radix、Ant Design X、手写 Tailwind、inline style；未引用的备用入口样式文件已在 2026-06-04 入口收缩时删除。
- 构建包体偏大，Markdown、Markmap、Model 页面和主包需要进一步按需加载。

### 2.2 目标架构

建议按 feature 拆分：

```text
src/app/                 App、router、providers
src/shared/api/          apiClient、healthClient、typed envelopes
src/shared/ui/           shadcn/Radix 基础组件和统一样式
src/features/tasks/      task DTO、task api、polling hook、task store
src/features/workspace/  Markdown、版本、面板状态、聊天、导图、卡片
src/features/settings/   provider/model/downloader/transcriber
src/features/library/    收藏、搜索、筛选、任务卡片
```

### 2.3 分阶段执行

P0：修确定 bug

- 修 `modelStore.addNewModel`：服务层已返回解包后的 data，不应再判断 `res.code`。
- 修健康检查 baseURL 拼接：提供 `joinApiPath(base, path)`，避免 `/api/api`。
- `useCheckBackend` 改用无 toast 的 `healthClient`，增加取消标记。
- `useTaskPolling` 对网络错误使用 retry/backoff，不把单次请求异常直接标成任务失败。

P1：API 层类型化

- `utils/request.ts` 拆为 `apiClient` 和 `healthClient`。
- services 只返回 typed DTO，不直接 toast；用户提示放在页面或 action 层。
- [x] 任务相关 service 已新增 typed `TaskSnapshot` normalizer；全局 `ApiEnvelope<T>` 和非任务 service 仍需继续收口。
- `LibraryPage`、`BackendHealthIndicator`、`useCheckBackend` 都复用同一个 API base 解析函数。

P2：任务状态和 store 拆分

- `taskStore` 只保留本地状态：`tasks/currentTaskId/workspaceSelection`。
- 任务提交、重试、删除、收藏同步、轮询迁到 `features/tasks/actions` 或 hook。
- [x] 任务 API 边界已通过 `normalizeTaskSnapshot` 初步分离服务端 DTO 与本地 UI task；`markdown: string | Markdown[]` 的内部形态还需继续统一。

P3：工作区拆组件

- `MarkdownViewer.tsx` 拆为：
  - [x] `WorkspaceStatusView`
  - [x] `MarkdownDocument`
  - `VersionSelector`
  - `WorkspaceToolbar`
  - `WorkspacePanels`
  - [x] `TaskFailureView`
- 用 React context 或 Zustand slice 替代 `window.dispatchEvent`。
- Markmap、Chat、KnowledgeCards 用动态 import，只有切换到对应面板时加载。

P4：资料库和设置页治理

- `LibraryPage/index.tsx` 拆搜索筛选、任务卡片、删除确认、空状态。
- 设置页 provider/model/downloader/transcriber 使用统一 form pattern。
- 已删除未引用的备用入口样式文件；后续继续明确 shadcn/Radix 为基础组件，Ant Design X 只用于聊天相关能力。

P5：性能门禁

- 给 Vite build 增加 bundle 分析或 size-limit。
- 设置 chunk 预算：首屏主包、Markdown 包、Markmap 包分别追踪。
- 对长任务列表和 Markdown 渲染加 memo/virtualization 策略。

## 3. 浏览器扩展重构方案

### 3.1 主要问题

扩展目录里有完整功能源码，但当前实际构建和 manifest 只接入 popup：

- `src/manifest.ts` 只声明 `action.default_popup`，没有 `background.service_worker`、`content_scripts`、`options_ui`、`side_panel`。
- `vite.config.mts` 只把 `src/popup/index.html` 作为 input。
- `scripts/prepare.ts` 只 stub `popup`。
- `package.json` 的 `dev/build` 没有调用 `vite.config.background.mts` 和 `vite.config.content.mts`。
- `types.ts` 的 `Settings` 只有 `backendUrl`，但 background/options/chat 使用 `providerId/modelName/formats/quality/style/video_understanding/grid_size`。
- `logic/api.ts` 只导出 Cookie 和 `ping`，但 options/sidepanel/chat 导入了 `getProviders/getModelsByProvider/getTaskStatus/askChat/resolveImageUrl` 等不存在函数。
- `tsconfig.json` include 过窄，没有覆盖 background、contentScripts、options、sidepanel，所以类型断裂被隐藏。
- E2E 仍是 Vitesse 模板断言，不能验证 Reel Mind 功能。

### 3.2 必须先定范围

扩展需要先二选一：

方案 A：Cookie Sync MVP

- 扩展只保留 popup Cookie 同步。
- 删除或隔离未接入的 background/content/sidepanel/options 高级页面。
- README、manifest、package scripts 全部改成 Cookie Sync 口径。

方案 B：完整视频笔记扩展

- popup、options、background、content script、sidepanel 全部纳入 manifest 和 build。
- 补齐类型、API、storage、权限、测试。

如果项目目标是长期产品，建议选 B；但执行顺序必须先“构建可验证”，再做 UI 功能。

### 3.3 分阶段执行

P0：修构建链

- 明确使用 pnpm 还是 npm。扩展 `packageManager` 是 pnpm，但当前机器没有 pnpm，npm 又找不到本地依赖。需要统一安装和脚本入口。
- 扩大 `tsconfig.json` include，覆盖所有 `src/**/*.ts` 和 `src/**/*.vue`。
- 先让 `typecheck` 暴露真实错误，再补类型。

P1：补 manifest 和 build

- manifest 增加：
  - `background.service_worker`
  - `content_scripts`
  - `options_ui`
  - `side_panel`
  - 对应权限：`contextMenus`、`sidePanel`，开发 HMR 权限只在 dev 开。
- package scripts 同时构建 popup/background/contentScripts/options/sidepanel，或改成一个多入口 Vite 配置。
- `scripts/prepare.ts` 生成所有 HTML stub。

P2：补 logic 契约

- `types.ts` 定义完整 `Settings`、`TaskRecord`、`TaskStatus`、`Provider`、`Model`、`NoteFormat`。
- `storage.ts` 增加 `tasks/tasksReady/upsertTask`。
- `api.ts` 补齐 options、sidepanel、chat 所需接口。

P3：统一消息流

- 所有生成笔记入口都走 background `startTask`。
- popup/content/right-click 只发消息，不直接写任务。
- 任务历史由 background 或统一 storage service 负责。

P4：安全和注入硬化

- content script 增加重复注入保护、SPA URL 变化处理、body 未就绪处理。
- Markdown 渲染做链接和图片协议白名单。
- 后端 URL 默认限制 localhost/127.0.0.1，用户输入非本地地址时明确提示风险。

P5：真实测试

- 替换 Vitesse E2E。
- 增加 manifest 结构测试、API wrapper 单测、storage 单测、background 消息流测试、content script 重复注入测试。

## 4. 工程化与部署重构方案

### 4.1 当前问题

- CI 偏发布构建，不是 PR 质量门禁。`main.yml`、`docker-build.yml`、`release-extension.yml` 多在 tag/workflow_dispatch 跑。
- 前端同时存在 `package-lock.json` 和 `pnpm-lock.yaml`；Docker/CI 用 pnpm，README/run.bat 用 npm。
- README 的预览图 `doc/image1.png`、`doc/image3.png`、`doc/image4.png` 当前不存在。
- `Dockerfile.complete` 单镜像路径存在 nginx 代理风险：把 `frontend:80` 改成 `127.0.0.1:8080`，但没有启动 8080 前端服务。
- compose 三容器部署和 `Dockerfile.complete` 单镜像发布是两套结构。
- `docker-compose.yml` 挂载 `./backend:/app`，适合开发/演示，但不是不可变生产镜像。
- 根 `.env.example` 和 `backend/.env.example` 口径不一致。
- 扩展默认后端 URL 是 `http://127.0.0.1:3015`，但设置页提示仍是 `http://localhost:8483`。

### 4.2 第一阶段：收缩本地启动入口，不再默认使用 Docker

重构第一步先不碰大架构，先把项目的“怎么启动”收缩到一个本地入口。当前 Docker、README、run.bat、CI、扩展默认地址和 nginx 配置同时存在多套口径，会让后续任何改动都很难判断“到底哪个入口是准的”。

第一阶段目标：

- 默认启动路径改为本地启动，不再要求用户先装 Docker 或执行 `docker compose up`。
- 根目录只保留一个主启动入口，例如 `run.bat` 或 `scripts/start-local.ps1`，它负责启动后端和前端。
- README 第一屏只写本地启动命令；Docker 入口下沉到“可选部署/历史兼容”章节。
- 后端、前端、扩展默认端口统一，建议保留当前产品默认入口 `http://127.0.0.1:3015`，后端 API 继续使用一个固定端口，例如 `8483`。
- Docker 相关部署文件暂时不删除，但不再作为推荐路径；根目录旧 Docker 启动脚本已删除，后续再决定修复、下线或保留三容器 compose。
- `docker-compose.yml`、`Dockerfile.complete`、`nginx/default.conf` 不作为第一阶段默认启动验收对象，避免一开始被部署细节拖住；根目录只保留 `run.bat` 一个 Windows 入口。

建议本地启动入口行为：

```text
根目录 run.bat / scripts/start-local.ps1
  1. 检查 backend\.venv 是否存在，不存在则提示创建虚拟环境和安装依赖。
  2. 设置 Windows 友好的 TMP/TEMP 到工作区临时目录。
  3. 启动后端：backend\.venv\Scripts\python.exe main.py 或 uvicorn backend.main:app。
  4. 启动前端：进入 reel-mind-frontend，使用统一包管理器执行 dev。
  5. 打印访问地址：http://127.0.0.1:3015。
```

这一阶段的验收标准：

- 新用户不看 Docker 文档，只按 README 的本地启动命令即可打开前端。
- `/api/sys_check` 能通过前端代理或本地 API 地址访问。
- README、run 脚本、前端 env、扩展默认后端 URL 不再互相矛盾。
- Docker 文档只标注为可选，不再写成推荐启动方式。

### 4.3 后续分阶段执行

P0：统一包管理和启动口径

- 在本地启动入口稳定后，再统一包管理器。前端建议统一 pnpm，因为现有 Docker/CI 已使用 `pnpm-lock.yaml`。
- 删除或停止维护 `reel-mind-frontend/package-lock.json`。
- README、run.bat、CI、Dockerfile 都统一到同一包管理器；但 README 的主入口必须仍然是本地启动，不是 Docker。
- 后端测试文档加入 Windows 本地建议：必要时把 `TMP/TEMP` 指到工作区临时目录。

P1：新增 PR 质量门禁

新增 workflow：

- backend：安装 dev requirements，跑 pytest。
- frontend：安装依赖，跑 lint + build。
- extension：安装依赖，跑 typecheck + test + build。
- docker：跑 `docker compose config`，关键路径做 smoke test。

P2：部署模式收敛

- Docker 不作为本地默认启动路径。三容器 compose 只作为可选演示/部署路径。
- 修复或下线 `Dockerfile.complete`。如果保留单镜像，nginx 应直接 serve `/usr/share/nginx/html`，只代理 `/api` 到 `127.0.0.1:8483`。
- `nginx/default.conf` 不应写死后端端口，或明确 compose 不允许改 `BACKEND_PORT`。

P3：文档修正

- 补齐 README 预览图或删除引用。
- 清理 `CHANGELOG.md` 中 `BillNote_*` 旧名。
- 统一 `/api/sys_check` 和 `/api/sys_health` 的说明：前者用于连通，后者用于依赖健康。
- 扩展设置页默认后端说明与实际默认值一致。

P4：端到端验收

- 后端：`TestClient` 覆盖 `/generate_note`、`/tasks`、`/delete_task`、`/chat/*` 的 HTTP 合约。
- 前端：Playwright 覆盖后端初始化、填写链接、任务轮询、收藏回看、错误重试。
- 扩展：mock 后端，覆盖 Cookie 同步和 backend URL fallback。

## 5. 推荐执行顺序

第一批：1-2 天，修硬问题和门禁

1. 先收缩启动入口：README 和运行脚本统一到本地启动，不再默认使用 Docker。
2. 前端修 `modelStore`、健康检查 URL、`useCheckBackend` toast/取消、轮询网络抖动。
3. 后端修上传/image proxy 安全底线、ResponseWrapper HTTP status 兼容。
4. 工程化统一前端包管理器，新增基础 CI。
5. 扩展先决定 MVP 范围，并让 typecheck 覆盖所有源码。

第二批：3-5 天，收敛任务契约

1. 定义后端 `TaskSnapshot`。
2. DB 负责状态和轻量元数据，文件只负责大体积产物。
3. 前端 `taskStore` 拆服务端任务和 UI 状态。
4. 删除任务、重试任务、轮询任务使用同一 typed service。

第三批：1 周，拆前端工作区和后端用例层

1. 拆 `MarkdownViewer`、`LibraryPage`。
2. 用 context/store slice 替代 `window.dispatchEvent`。
3. 后端 router 改 `Depends`，DAO 改 session 注入。
4. `NoteGenerator` 变成可测试 pipeline。

第四批：1 周，扩展完整化或瘦身

1. 如果选 Cookie Sync MVP，删/隔离未接入功能。
2. 如果选完整扩展，补 manifest/build/types/api/storage/message flow。
3. 替换模板 E2E。

第五批：持续改进

1. Chat/verification 模块深拆。
2. Bundle size 预算和按需加载。
3. Docker 单镜像/三容器策略最终定稿；如果本地启动已经满足课程/演示需要，可以直接下线复杂 Docker 路径。
4. 安全策略：本地 token、CORS、上传、代理、扩展权限最小化。

## 6. 验收标准

重构不应只以“能跑”为标准。建议每个阶段至少满足：

- `backend\.venv\Scripts\python.exe -m pytest` 通过。
- 前端 lint + build 通过，首屏主包和重依赖 chunk 有预算记录。
- 扩展 typecheck 覆盖所有源码，build 产物与 manifest 声明一致。
- 本地启动入口能启动前后端，`/api/sys_check` 和 `/api/sys_health` 语义清楚。
- Docker compose 如果保留，应作为可选路径单独验证，不再作为默认启动验收项。
- 核心 API 有 HTTP 合约测试。
- README 的启动命令、端口、截图、扩展说明与实际代码一致。
- 不新增隐式全局状态；新服务通过显式依赖注入或统一配置创建。
