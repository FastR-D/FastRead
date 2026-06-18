# ReelMind 后端重构交接记录

更新时间：2026-05-18

## 当前目标

用户明确要求不做“最小可用改动”，远端已有备份，可以按工程质量继续大幅重构。当前主线是把后端笔记生成、任务管理、结果产物、联网核验等混杂职责拆清楚，保持 API 行为稳定。

## 环境

仓库根目录：

```powershell
C:\Users\Lenovo\Desktop\schoolwork\reelmind
```

后端测试命令：

```powershell
backend\.venv\Scripts\python.exe -m pytest
```

前端构建命令：

```powershell
cd reel-mind-frontend
npm run build
```

说明：Vite/esbuild 在沙箱内可能因为目录权限报 `Access is denied`，需要在正常本机权限下运行。

## 本轮完成的结构拆分

### 1. 笔记产物仓库

新增：

- `backend/app/repositories/__init__.py`
- `backend/app/repositories/note_artifacts.py`

职责：

- 统一管理 `note_results` 下的结果、状态、音频缓存、转写缓存、Markdown 缓存文件。
- 提供 JSON 读写、状态写入、结果文件枚举、任务产物删除。
- 替代散落在 router/service 中的直接文件访问。

已迁移使用方：

- `backend/app/routers/note.py`
- `backend/app/services/chat_service.py`
- `backend/app/services/chat_tools.py`
- `backend/app/services/vector_store.py`
- `backend/app/services/note.py`

### 2. NoteGenerator 拆分

`backend/app/services/note.py` 已从大块流程拆成多个服务：

- `backend/app/services/transcript_service.py`
  - 预取字幕缓存
  - 平台字幕获取
  - ASR fallback
  - 转写元数据补全
- `backend/app/services/media_service.py`
  - 音频元数据缓存
  - metadata-only 下载
  - 视频下载
  - 视频理解拼图
  - 音频下载
- `backend/app/services/summary_service.py`
  - GPTSource 构造
  - GPT 总结
  - Markdown 缓存
  - insights 构建
- `backend/app/services/post_process_service.py`
  - 来源链接
  - 时间戳链接替换
  - 截图标记替换
- `backend/app/services/note_lifecycle_service.py`
  - 任务状态写入
  - 异常消息格式化
  - DB metadata 保存
  - 删除笔记 DB 记录

当前 `NoteGenerator` 约 252 行，主要保留生成流水线编排。

### 3. note 路由瘦身

新增：

- `backend/app/services/note_task_service.py`

迁移出 `backend/app/routers/note.py` 的职责：

- 生成任务准备
- 后台任务执行封装
- 任务删除及向量索引删除
- 收藏信息更新
- 在线核验任务
- 任务列表拼装
- 任务状态响应拼装
- 预取字幕清洗和持久化
- 旧笔记 insights 按需补全

当前 `backend/app/routers/note.py` 约 232 行，只保留请求模型、路由函数和响应包装。

### 4. GPT/provider 构造统一

新增：

- `backend/app/services/gpt_provider.py`

迁移重复逻辑：

- `backend/app/services/note.py`
- `backend/app/services/chat_service.py`
- `backend/app/services/online_verifier.py`

现在统一通过：

```python
GPTProvider.create(provider_id=..., model_name=...)
```

说明：

- `required=True` 时找不到 provider 会抛 `ProviderError`。
- `required=False` 时返回 `None`，用于联网核验这种可选 AI verifier 场景。

## 新增测试

新增或更新：

- `backend/tests/test_note_artifact_repository.py`
- `backend/tests/test_transcript_service.py`
- `backend/tests/test_media_service.py`
- `backend/tests/test_summary_service.py`
- `backend/tests/test_post_process_service.py`
- `backend/tests/test_note_task_service.py`
- `backend/tests/test_gpt_provider.py`
- `backend/tests/test_note_lifecycle_service.py`
- `backend/tests/test_online_verifier_brave.py`

## 当前验证结果

后端测试已通过：

```powershell
backend\.venv\Scripts\python.exe -m pytest
```

结果：

```text
69 passed
```

前端构建已通过：

```powershell
cd reel-mind-frontend
npm run build
```

结果：构建成功。

仍有既有警告，不是本轮引入：

- `node_modules/lottie-web/...` 使用 `eval`
- 部分 chunk 超过 500 kB

## 2026-05-20 追加：online_verifier 拆分进展

本轮继续拆 `backend/app/services/online_verifier.py`，保持 `verify_claims_online`、`search_web`、`search_web_multi` 以及原有私有 helper 名称兼容，现有测试里直接 patch `online_verifier.search_brave` 的用法仍可工作。

新增子包：

- `backend/app/services/verification/__init__.py`
- `backend/app/services/verification/constants.py`
- `backend/app/services/verification/text_utils.py`
- `backend/app/services/verification/search_providers.py`
- `backend/app/services/verification/numeric_evidence.py`
- `backend/app/services/verification/query_builder.py`
- `backend/app/services/verification/ai_judge.py`
- `backend/app/services/verification/relevance.py`

已迁出的职责：

- 搜索源配置、Brave/Bing/Baidu/DuckDuckGo/Wikipedia 请求与解析。
- 搜索结果 URL 清洗、域名提取、可信来源判断、低价值来源过滤。
- 数字主张提取、数字证据匹配/冲突判定、数字证据指标。
- 科学/学术/领域词查询构造。
- AI verifier 初始化、上下文 profile、AI query rewrite、AI judge。
- 相关度判断、结果过滤、证据评分。

`online_verifier.py` 当前约 574 行，主要保留：

- 兼容用薄 wrapper。
- 多搜索源补充检索编排。
- 默认 rule-based online verdict。
- numeric verdict enforcement。
- `verify_claims_online` 总流程。

测试结果：

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_online_verifier_brave.py
# 11 passed

backend\.venv\Scripts\python.exe -m pytest
# 69 passed
```

测试装载注意：

- `backend/tests/test_online_verifier_brave.py` 使用 stub 隔离导入 `online_verifier.py`。
- 新增 `app.services.__path__`，让测试能加载真实 `app.services.verification` 子包。
- 每次加载前清理 `app.services.verification*`，避免环境变量配置被子模块缓存导致用例串扰。

## 2026-05-20 追加：online_verifier 第二轮优化

本轮继续瘦身 `backend/app/services/online_verifier.py`，保持旧测试 patch 入口兼容：

- 新增 `backend/app/services/verification/verdict.py`
  - rule-based online verdict
  - numeric verdict enforcement
  - claim 汇总状态、分数、summary 计算
- 新增 `backend/app/services/verification/search_orchestrator.py`
  - `search_web_multi` 多查询、多 provider、补充搜索和 fallback 结果编排
  - 支持注入 `search_with_provider_fn` / `provider_results_fn` / `relevance_fn`，用于兼容现有测试 patch
- 新增 `backend/tests/test_verification_modules.py`
  - 直接覆盖 query builder、numeric evidence、relevance、verdict、search orchestrator

`online_verifier.py` 当前约 421 行，主要剩：

- 对旧私有 helper 名称的兼容 wrapper。
- provider dispatch wrapper，用于支持测试直接 patch `online_verifier.search_brave` / `_provider_results`。
- `verify_claims_online` 主流程。

本轮验证：

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_verification_modules.py
# 5 passed

backend\.venv\Scripts\python.exe -m pytest backend\tests\test_online_verifier_brave.py
# 11 passed

backend\.venv\Scripts\python.exe -m pytest
# 74 passed
```

## 当前关键行为约束

这轮重构尽量保持 API 行为不变。

笔记生成顺序仍是：

1. 解析平台和模型 provider
2. 优先读取预取字幕或平台字幕
3. 下载媒体或 metadata-only
4. 无字幕时执行 ASR
5. 转写结果补元数据并写缓存
6. GPT 生成 Markdown
7. 链接、截图、来源链接后处理
8. 基于最终 Markdown 构建 insights
9. 保存 DB metadata
10. 写入成功状态
11. 后台任务外层保存最终 result JSON
12. 尝试建立向量索引，失败不影响笔记

已修正的结构性问题：

- 总结阶段状态不再误写到 `*_markdown.status.json`。
- 真实 `task_id` 贯穿状态文件。
- 截图、链接、向量索引等非核心后处理失败仍按原逻辑容错。

## 当前工作区注意事项

工作区本来就有很多脏文件，其中有不少不是本轮改的。不要随手 revert。

本轮明确新增或修改的后端重构相关文件包括：

- `backend/app/repositories/__init__.py`
- `backend/app/repositories/note_artifacts.py`
- `backend/app/services/note.py`
- `backend/app/services/note_task_service.py`
- `backend/app/services/note_lifecycle_service.py`
- `backend/app/services/gpt_provider.py`
- `backend/app/services/transcript_service.py`
- `backend/app/services/media_service.py`
- `backend/app/services/summary_service.py`
- `backend/app/services/post_process_service.py`
- `backend/app/services/chat_service.py`
- `backend/app/services/chat_tools.py`
- `backend/app/services/vector_store.py`
- `backend/app/services/online_verifier.py`
- `backend/app/routers/note.py`
- 上面列出的测试文件

已知还有其他预先存在或其他任务产生的脏文件，例如：

- `.env.example`
- `README.md`
- `backend/.env.example`
- `backend/app/routers/chat.py`
- `backend/app/services/online_verifier.py`
- 若干前端文件
- `run.bat`
- 旧 Docker 启动脚本（2026-06-04 入口收缩后已下线删除，默认只保留 `run.bat`）
- `task/ReelMind_PRD_汇报版.md`

如果下个对话继续改，先看 `git status --short`，不要假设所有改动都属于当前任务。

## 建议下一步

`online_verifier.py` 已完成两轮结构拆分。后续建议按风险从低到高继续：

1. 把 `online_verifier.py` 里的兼容 wrapper 逐步减少，只保留被测试或外部调用确实依赖的导出。
2. 把 `test_online_verifier_brave.py` 中对私有 helper 的断言逐步迁到 `test_verification_modules.py`。
3. 再考虑抽 `domain_rules.py`，统一维护红黑树、LeMay、蛋白质等领域特例。
4. 最后把 `verify_claims_online` 封成类或小服务，主模块只保留对外函数。

每步都跑：

```powershell
backend\.venv\Scripts\python.exe -m pytest
```

如果改动影响前端数据结构，再跑：

```powershell
cd reel-mind-frontend
npm run build
```

## 下个对话可直接使用的上下文

可以直接告诉下个模型：

1. 仓库在 `C:\Users\Lenovo\Desktop\schoolwork\reelmind`
2. 最新交接文件是 `readme/handoff-2026-05-18-backend-refactor.md`
3. 后端重构已经完成第一阶段：
   - 产物仓库
   - 生成流水线拆分
   - note 路由瘦身
   - GPT provider 工厂
   - lifecycle side effects 拆分
4. 当前验证是 `74 passed`，前端 build 通过但有既有 warning
5. 下一步优先减少 `online_verifier.py` 的兼容 wrapper，或抽 `domain_rules.py`
