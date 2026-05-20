import { useState, useEffect, useCallback, useMemo } from 'react'
import { Bubble, Sender } from '@ant-design/x'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Loader2, Trash2, ChevronDown, ChevronUp, BookOpen, UserRound, Bot, Maximize2, Minimize2, Library } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useChatStore } from '@/store/chatStore'
import { useTaskStore } from '@/store/taskStore'
import { askQuestion, getChatStatus, indexTask, type ChatSource, type IndexStatus } from '@/services/chat'

type ChatMode = 'half' | 'full'

interface ChatPanelProps {
  taskId: string
  mode: ChatMode
  onModeChange: (mode: ChatMode) => void
}

function SourceBadges({ sources }: { sources: ChatSource[] }) {
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
          {sources.map((s, i) => (
            <Badge key={i} variant="outline" className="text-xs font-normal">
              {s.title
                ? `${s.title.slice(0, 16)} · ${s.source_type === 'markdown' ? '笔记' : s.source_type === 'meta' ? '信息' : '转录'}`
                : s.source_type === 'markdown'
                ? s.section_title || '笔记'
                : `${(s.start_time ?? 0).toFixed(0)}s ~ ${(s.end_time ?? 0).toFixed(0)}s`}
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ChatPanel({ taskId, mode, onModeChange }: ChatPanelProps) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null)
  const [scope, setScope] = useState<'task' | 'library'>('task')
  const chatKey = scope === 'library' ? 'library' : taskId

  const storedMessages = useChatStore(state => state.chatHistory[chatKey])
  const messages = useMemo(() => storedMessages ?? [], [storedMessages])
  const addMessage = useChatStore(state => state.addMessage)
  const clearChat = useChatStore(state => state.clearChat)

  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const tasks = useTaskStore(state => state.tasks)
  const currentTask = useMemo(
    () => tasks.find(t => t.id === currentTaskId) ?? null,
    [tasks, currentTaskId],
  )

  const modelTask = useMemo(
    () => currentTask || tasks.find(t => t.formData?.provider_id && t.formData?.model_name) || null,
    [currentTask, tasks],
  )

  // 检查索引状态。索引只是增强能力，不能阻塞基础问答。
  useEffect(() => {
    if (scope === 'library') {
      setIndexStatus('indexed')
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

        if (res.status === 'indexing') {
          timer = setTimeout(poll, 2000)
        }
      } catch {
        if (!cancelled) setIndexStatus('idle')
      }
    }

    poll()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [taskId, scope])

  const handleSend = useCallback(
    async (value: string) => {
      const question = value.trim()
      if (!question || loading) return

      const providerId = modelTask?.formData?.provider_id
      const modelName = modelTask?.formData?.model_name
      if (!providerId || !modelName) {
        toast.error('无法获取模型配置，请确认任务已完成')
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
        })
      } catch {
        toast.error('问答请求失败')
      } finally {
        setLoading(false)
      }
    },
    [loading, taskId, chatKey, scope, modelTask, messages, addMessage],
  )

  // 转换为 Bubble.List 的数据格式
  const bubbleItems = useMemo(() => {
    const items = messages.map((msg, i) => ({
      key: `msg-${i}`,
      role: msg.role === 'user' ? ('user' as const) : ('ai' as const),
      content: msg.content,
      footer:
        msg.role === 'assistant' && msg.sources ? (
          <SourceBadges sources={msg.sources} />
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
  }, [messages, loading])

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
        contentRender: (content: any) => (
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
          <span className="text-sm font-medium">AI 问答</span>
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
            title={scope === 'task' ? '切换到知识库问答' : '切换到当前视频问答'}
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
                {indexStatus === 'indexing'
                  ? '向量索引正在后台构建，当前仍可基于笔记内容提问。'
                  : '当前使用基础检索，可直接提问；需要更准召回时再建立向量索引。'}
              </span>
              <Button
                size="sm"
                variant="outline"
                className="h-7 shrink-0 border-amber-300 bg-white px-2 text-xs hover:bg-amber-100"
                disabled={indexStatus === 'indexing'}
                onClick={async () => {
                  setIndexStatus('indexing')
                  try {
                    await indexTask(taskId)
                  } catch {
                    toast.error('索引请求失败')
                    setIndexStatus('failed')
                  }
                }}
              >
                {indexStatus === 'indexing' ? '索引中' : '建立索引'}
              </Button>
            </div>
          </div>
        )}
        {messages.length === 0 && !loading ? (
          <div className="flex h-full items-center justify-center text-center text-sm text-neutral-400">
            <div>
              <p>针对笔记内容提问</p>
              <p className="mt-1 text-xs">
                {scope === 'task' ? '例如：这个视频的核心观点是什么？' : '例如：这些视频共同提到的行动建议是什么？'}
              </p>
            </div>
          </div>
        ) : (
          <Bubble.List
            items={bubbleItems}
            role={roles}
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
          placeholder="输入你的问题..."
        />
      </div>
    </div>
  )
}
