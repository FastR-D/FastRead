import { useState, useEffect, useCallback, useMemo } from 'react'
import { Bubble, Sender } from '@ant-design/x'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Trash2, ChevronDown, ChevronUp, BookOpen, UserRound, Bot, Maximize2, Minimize2, Library, ExternalLink } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useChatStore } from '@/store/chatStore'
import { useTaskStore } from '@/store/taskStore'
import { useModelStore } from '@/store/modelStore'
import { askQuestion, getChatStatus, indexTask, type ChatSource, type IndexStatus } from '@/services/chat'
import { resolve_backend_resource_url } from '@/services/note'
import { emitWorkspaceCommand } from '@/utils/workspaceNavigation'

type ChatMode = 'half' | 'full'

interface ChatPanelProps {
  taskId: string
  mode: ChatMode
  onModeChange: (mode: ChatMode) => void
}

function SourceBadges({
  sources,
  onOpenSource,
}: {
  sources: ChatSource[]
  onOpenSource: (source: ChatSource) => void
}) {
  const [expanded, setExpanded] = useState(false)

  if (!sources || sources.length === 0) return null

  return (
    <div className="mt-1.5">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-xs text-neutral-400 hover:text-neutral-600"
      >
        <BookOpen className="h-3 w-3" />
        <span>引用来源 ({sources.length})</span>
        {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
      </button>
      {expanded && (
        <div className="mt-1 flex flex-wrap gap-1">
          {sources.map((source, index) => {
            const pageLabel = source.page_start
              ? `第 ${source.page_start}${source.page_end && source.page_end !== source.page_start ? `–${source.page_end}` : ''} 页`
              : '论文原文'
            const typeLabel = pageLabel
            const label = source.title ? `${source.title.slice(0, 24)} · ${typeLabel}` : typeLabel
            const href = resolve_backend_resource_url(source.source_url)
              || (source.doi ? `https://doi.org/${source.doi.replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, '')}` : '')
            const canLocate = source.source_type === 'paper_page' && Boolean(source.page_start)
            const badge = (
              <Badge variant="outline" className="gap-1 text-xs font-normal">
                {label}
                {href && !canLocate && <ExternalLink className="h-2.5 w-2.5" />}
              </Badge>
            )

            if (canLocate) {
              return (
                <button
                  key={`${source.task_id || ''}:${source.page_start}:${index}`}
                  type="button"
                  onClick={() => onOpenSource(source)}
                  title="在分页原文中定位并高亮引用"
                  className="rounded transition hover:bg-amber-50"
                >
                  {badge}
                </button>
              )
            }

            return href ? (
              <a key={`${source.source_url || source.doi || index}`} href={href} target="_blank" rel="noreferrer" title="打开引用原文">
                {badge}
              </a>
            ) : (
              <span key={index}>{badge}</span>
            )
          })}
        </div>
      )}
    </div>
  )
}

const groundingLabels: Record<string, string> = {
  source_grounded: '原文引用已校验',
  source_context_supplied: '已提供原文上下文',
  retrieval_miss: '未检索到匹配段落',
  requested_page_missing: '指定页码不可用',
  response_format_invalid: '回答格式校验失败',
  citation_missing: '回答缺少原文引用',
  citation_rejected: '引用校验未通过',
  insufficient_source: '已检索，但证据不足',
}

function GroundingNotice({
  status,
  detail,
  strategy,
  pages,
}: {
  status?: string
  detail?: string
  strategy?: string
  pages?: number[]
}) {
  if (!status) return null
  const verified = status === 'source_grounded'
  const pageText = pages?.length ? ` · 检索页 ${pages.join('、')}` : ''
  const title = [detail, strategy ? `检索策略：${strategy}` : ''].filter(Boolean).join('；') || undefined
  return (
    <div
      className={`mt-1.5 rounded border px-2 py-1 text-[11px] ${verified ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-800'}`}
      title={title}
    >
      <span className="font-medium">{groundingLabels[status] || status}</span>
      {pageText}
    </div>
  )
}

export default function ChatPanel({ taskId, mode, onModeChange }: ChatPanelProps) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null)
  const [indexDetail, setIndexDetail] = useState('')
  const [indexPollNonce, setIndexPollNonce] = useState(0)
  const [scope, setScope] = useState<'task' | 'library'>('task')
  const chatKey = scope === 'library' ? 'library' : taskId

  const storedMessages = useChatStore(state => state.chatHistory[chatKey])
  const messages = useMemo(() => storedMessages ?? [], [storedMessages])
  const addMessage = useChatStore(state => state.addMessage)
  const clearChat = useChatStore(state => state.clearChat)

  const tasks = useTaskStore(state => state.tasks)
  const task = useMemo(
    () => tasks.find(item => item.id === taskId) ?? null,
    [tasks, taskId],
  )
  const modelList = useModelStore(state => state.modelList)
  const loadEnabledModels = useModelStore(state => state.loadEnabledModels)

  useEffect(() => {
    if (modelList.length === 0) loadEnabledModels()
  }, [loadEnabledModels, modelList.length])

  const model = useMemo(() => {
    const reportModel = task?.insights?.reading_report?.model
    const providerId = task?.paperInput.provider_id || reportModel?.provider_id
    const modelName = task?.paperInput.model_name || reportModel?.model_name
    if (providerId || modelName) {
      return modelList.find(item =>
        item.provider_id === providerId && item.model_name === modelName
      )
    }
    return modelList[0]
  }, [modelList, task?.paperInput.model_name, task?.paperInput.provider_id, task?.insights?.reading_report?.model])
  const suggestedQuestions = task?.insights?.reading_report?.suggested_questions || []

  const openSource = useCallback((source: ChatSource) => {
    const quote = (source.exact_quote || source.text || '').trim().slice(0, 800) || undefined
    emitWorkspaceCommand({
      taskId: source.task_id || taskId,
      viewMode: 'source',
      page: source.page_start,
      quote,
    })
  }, [taskId])

  // 检查索引状态。索引只是增强能力，不能阻塞基础问答。
  useEffect(() => {
    if (scope === 'library') {
      setIndexStatus('indexed')
      setIndexDetail('')
      return
    }
    if (!taskId) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const poll = async () => {
      try {
        const res = await getChatStatus(taskId)
        if (cancelled) return
        setIndexStatus(res.status)
        setIndexDetail(res.detail || '')

        if (res.status === 'idle') {
          const started = await indexTask(taskId)
          if (cancelled) return
          setIndexStatus(started.status)
          setIndexDetail(started.detail || '')
          if (started.status === 'indexing') timer = setTimeout(poll, 2000)
          return
        }
        if (res.status === 'indexing') {
          timer = setTimeout(poll, 2000)
        }
      } catch (error) {
        if (!cancelled) {
          setIndexStatus('failed')
          setIndexDetail(error instanceof Error ? error.message : '索引状态检查失败')
        }
      }
    }

    poll()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [taskId, scope, indexPollNonce])

  const handleSend = useCallback(
    async (value: string) => {
      const question = value.trim()
      if (!question || loading) return

      const providerId = model?.provider_id
      const modelName = model?.model_name
      if (!providerId || !modelName) {
        toast.error('持续追问需要模型，请先在设置中启用一个模型')
        return
      }

      addMessage(chatKey, { role: 'user', content: question })
      setInput('')
      setLoading(true)

      try {
        const history = messages.map(m => ({ role: m.role, content: m.content }))
        const res = await askQuestion({
          task_id: scope === 'task' ? taskId : undefined,
          scope,
          question,
          history,
          provider_id: providerId,
          model_name: modelName,
        })
        addMessage(chatKey, {
          role: 'assistant',
          content: res.answer,
          sources: res.sources,
          groundingStatus: res.grounding_status,
          groundingDetail: res.grounding_detail,
          retrievalStrategy: res.retrieval_strategy,
          retrievedPages: res.retrieved_pages,
        })
      } catch {
        toast.error('问答请求失败')
      } finally {
        setLoading(false)
      }
    },
    [loading, taskId, chatKey, scope, model, messages, addMessage],
  )

  // 转换为 Bubble.List 的数据格式
  const bubbleItems = useMemo(() => {
    const items = messages.map((msg, i) => ({
      key: `msg-${i}`,
      role: msg.role === 'user' ? ('user' as const) : ('ai' as const),
      content: msg.content,
      footer: msg.role === 'assistant' ? (
        <div>
          <GroundingNotice
            status={msg.groundingStatus}
            detail={msg.groundingDetail}
            strategy={msg.retrievalStrategy}
            pages={msg.retrievedPages}
          />
          {msg.sources?.length ? <SourceBadges sources={msg.sources} onOpenSource={openSource} /> : null}
        </div>
      ) : undefined,
    }))

    if (loading) {
      items.push({
        key: 'loading',
        role: 'ai' as const,
        content: '思考中...',
        loading: true,
      } as any)
    }

    return items
  }, [messages, loading, openSource])

  // Bubble 角色配置
  const roles = useMemo(
    () => ({
      user: {
        placement: 'end' as const,
        avatar: (
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-500 text-white">
            <UserRound className="h-4 w-4" />
          </div>
        ),
        variant: 'filled' as const,
        styles: { content: { background: '#3b82f6', color: '#fff' } },
      },
      ai: {
        placement: 'start' as const,
        avatar: (
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-neutral-500 text-white">
            <Bot className="h-4 w-4" />
          </div>
        ),
        variant: 'outlined' as const,
        messageRender: (content: any) => (
          <div className="markdown-body prose prose-sm max-w-none prose-p:my-1 prose-li:my-0.5 prose-headings:my-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {typeof content === 'string' ? content : String(content)}
            </ReactMarkdown>
          </div>
        ),
      },
    }),
    [],
  )

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden border-l bg-white">
      {/* 头部 */}
      <div className="flex shrink-0 items-center justify-between border-b px-3 py-2">
        <div className="min-w-0">
          <span className="text-sm font-medium">{scope === 'task' ? '带页码追问' : '跨论文问答'}</span>
          {scope === 'task' && indexStatus !== 'indexed' && (
            <span className="ml-2 text-xs text-amber-600">
              {indexStatus === 'indexing' ? '索引构建中，基础问答可用' : '基础检索模式'}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant={scope === 'library' ? 'default' : 'ghost'}
            size="sm"
            className="h-7 px-2"
            onClick={() => setScope(scope === 'task' ? 'library' : 'task')}
            title={scope === 'task' ? '切换到跨论文问答' : '切换到当前论文问答'}
          >
            {scope === 'task' ? <BookOpen className="h-3.5 w-3.5" /> : <Library className="h-3.5 w-3.5" />}
            <span className="ml-1 text-xs">{scope === 'task' ? '当前' : '知识库'}</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-neutral-400 hover:text-neutral-600"
            onClick={() => onModeChange(mode === 'half' ? 'full' : 'half')}
            title={mode === 'half' ? '全屏' : '半屏'}
          >
            {mode === 'half' ? (
              <Maximize2 className="h-3.5 w-3.5" />
            ) : (
              <Minimize2 className="h-3.5 w-3.5" />
            )}
          </Button>
          {messages.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-neutral-400 hover:text-red-500"
              onClick={() => clearChat(chatKey)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>

      {/* 消息列表 */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {scope === 'task' && indexStatus !== 'indexed' && (
          <div className="mx-3 mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <div className="flex items-center justify-between gap-3">
              <span>
                {indexStatus === 'disabled'
                  ? `当前部署未启用向量索引；基础检索和带页码问答仍可使用。${indexDetail ? ` ${indexDetail}` : ''}`
                  : indexStatus === 'indexing'
                    ? '多语言向量索引正在后台准备；首次会下载约 0.22 GB 模型，当前仍可立即提问。'
                    : indexStatus === 'failed'
                      ? `向量索引建立失败，可重试；基础检索仍可使用。${indexDetail ? ` 原因：${indexDetail}` : ''}`
                      : '当前使用逐页关键词检索；向量索引会在后台自动建立。'}
              </span>
              <Button
                size="sm"
                variant="outline"
                className="h-7 shrink-0 border-amber-300 bg-white px-2 text-xs hover:bg-amber-100"
                disabled={indexStatus === 'indexing' || indexStatus === 'disabled'}
                onClick={async () => {
                  setIndexStatus('indexing')
                  setIndexDetail('')
                  try {
                    const result = await indexTask(taskId)
                    setIndexStatus(result.status)
                    setIndexDetail(result.detail || '')
                    if (result.status === 'indexing') setIndexPollNonce(value => value + 1)
                  } catch {
                    toast.error('索引请求失败')
                    setIndexStatus('failed')
                  }
                }}
              >
                {indexStatus === 'disabled' ? '部署未启用' : indexStatus === 'indexing' ? '索引中' : indexStatus === 'failed' ? '重试索引' : '建立索引'}
              </Button>
            </div>
          </div>
        )}
        {messages.length === 0 && !loading ? (
          <div className="flex h-full items-center justify-center text-center text-sm text-neutral-400">
            <div>
              <p>针对论文与阅读报告持续追问</p>
              <p className="mt-1 text-xs">
                {scope === 'task'
                  ? '可以问原文或阅读报告，也可以接着问“它在哪几页、为什么”；回答会优先引用论文原文页码。'
                  : '可跨论文比较共同结论与差异，也可以结合上一轮继续追问。'}
              </p>
              {scope === 'task' && suggestedQuestions.length > 0 && (
                <div className="mx-auto mt-4 flex max-w-md flex-wrap justify-center gap-2 px-4">
                  {suggestedQuestions.slice(0, 4).map(question => (
                    <button
                      key={question}
                      type="button"
                      onClick={() => handleSend(question)}
                      className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-left text-xs text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900"
                    >
                      {question}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <Bubble.List
            items={bubbleItems}
            roles={roles}
            style={{ minHeight: '100%', padding: '12px' }}
          />
        )}
      </div>

      {/* 输入区域 */}
      <div className="shrink-0 border-t bg-white px-3 py-2">
        <Sender
          value={input}
          onChange={setInput}
          onSubmit={handleSend}
          loading={loading}
          placeholder="可连续追问，例如：这个结论依据哪几页？"
        />
      </div>
    </div>
  )
}
