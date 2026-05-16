# ReelMind 创新功能交接记录

更新时间：2026-05-16

## 本轮目标

用户要求把三个创新功能加入项目：

- 知识卡片视图
- 信息密度 / 可信度 / 可执行性评分
- 跨视频知识库问答

本轮已完成实现和基础验证，代码尚未提交。

## 已完成改动

### 1. 后端结构化洞察

新增文件：

- `backend/app/services/insight_extractor.py`

主要能力：

- 从最终 Markdown、转录文本、视频元信息中生成 `insights`
- 输出结构包含：
  - `summary`
  - `scores.information_density`
  - `scores.credibility`
  - `scores.actionability`
  - `cards`
- 卡片类型包括：
  - `核心结论`
  - `知识要点`
  - `概念解释`
  - `操作步骤`
  - `风险提醒`
  - `行动清单`
  - `金句`

已修改：

- `backend/app/models/notes_model.py`
  - `NoteResult` 新增 `insights: Optional[dict] = None`
- `backend/app/services/note.py`
  - 生成笔记后调用 `build_insights(...)`
  - 保存到 `NoteResult.insights`
- `backend/app/routers/note.py`
  - `/tasks` 返回 `insights`
  - 对旧笔记按需即时生成临时 `insights`，不改写历史文件

说明：

- 当前评分是启发式规则，不额外调用 LLM，不消耗 token。
- 可信度会识别 `raw.source == "douyin_metadata"`，对只有元数据的内容降权。

### 2. 前端知识卡片视图

新增文件：

- `BillNote_frontend/src/pages/HomePage/components/KnowledgeCardsView.tsx`

已修改：

- `BillNote_frontend/src/store/taskStore/index.ts`
  - 新增 `NoteInsights`、`InsightScore`、`KnowledgeCard` 类型
  - `Task` 新增 `insights?: NoteInsights`
  - 恢复历史任务时读取 `task.insights`
- `BillNote_frontend/src/hooks/useTaskPolling.ts`
  - 任务成功后从结果中保存 `insights`
- `BillNote_frontend/src/pages/HomePage/components/MarkdownHeader.tsx`
  - `viewMode` 扩展为 `'preview' | 'map' | 'cards'`
  - 新增“知识卡片”按钮
- `BillNote_frontend/src/pages/HomePage/components/MarkdownViewer.tsx`
  - `viewMode === 'cards'` 时渲染 `KnowledgeCardsView`

当前 UI：

- 顶部显示三项评分卡：
  - 信息密度
  - 可信度
  - 可执行性
- 下方显示知识卡片网格。
- 旧笔记如果没有保存 `insights`，刷新任务列表后也能看到后端即时生成的卡片。

### 3. 跨视频知识库问答

已修改：

- `backend/app/routers/chat.py`
  - `AskRequest.task_id` 改为可选
  - 新增 `scope: "task" | "library" = "task"`
  - 当前视频模式仍要求 `task_id`
- `backend/app/services/chat_service.py`
  - 新增 `LIBRARY_SYSTEM_PROMPT`
  - 新增本地笔记文件召回逻辑：
    - 读取 `NOTE_OUTPUT_DIR/*.json`
    - 排除 `.status.json`、`_transcript.json`、`_audio.json`
    - 从 `meta`、`markdown`、`transcript` 生成 chunk
    - 使用轻量词法召回选出相关片段
  - `chat(..., scope="library")` 进入全库问答
- `BillNote_frontend/src/services/chat.ts`
  - `askQuestion` 支持 `scope?: 'task' | 'library'`
  - `task_id` 改为可选
  - `ChatSource` 增加 `task_id`、`title`、`meta/unknown` 来源类型
- `BillNote_frontend/src/pages/HomePage/components/ChatPanel.tsx`
  - 新增“当前 / 知识库”切换
  - 知识库模式跳过单视频向量索引
  - 知识库聊天记录使用 `library` 作为本地 key
  - 引用来源展示视频标题和来源类型

说明：

- 当前全库问答是 MVP 实现：不依赖 Chroma 全局索引，直接从本地结果文件做词法召回。
- 后续可以升级为全局向量索引或按收藏夹/标签过滤。

## 验证结果

已通过：

```powershell
python -m compileall backend/app
```

```powershell
cd BillNote_frontend
npm run build
```

构建提示：

- Vite 仍有既有的大 chunk 警告。
- `lottie-web` 仍有既有 eval 警告。
- 这些警告没有阻塞构建，不是本轮新增错误。

## 当前工作树注意事项

本轮功能改动未提交。

工作树中还保留了之前的 ReelMind 改名改动，也未提交。下一次继续时需要注意：

- 不要误回滚 ReelMind 改名相关文件。
- 如果准备提交，可以考虑一次提交包含：
  - ReelMind 统一命名
  - 本轮三个创新功能
- 或者先拆成两个提交：
  - `Rename project to ReelMind`
  - `Add insight cards and library QA`

## 下次建议

建议下一轮优先做三件事：

1. 手动跑一个真实抖音视频任务，确认结果 JSON 里写入 `insights`。
2. 打开前端验证“知识卡片”按钮和三项评分展示。
3. 用两条以上历史笔记测试“知识库”问答，观察召回来源是否足够准。

可继续优化方向：

- 把 `insights` 的生成从启发式升级为可选 LLM 精炼模式。
- 给知识卡片增加复制、收藏、导出 Anki/Notion 的能力。
- 给知识库问答增加收藏夹、标签、时间范围过滤。
- 为全库问答建立 Chroma 全局索引，替代当前词法召回。
