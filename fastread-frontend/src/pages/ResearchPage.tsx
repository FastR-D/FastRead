import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  ArchiveRestore,
  ArrowLeft,
  BookOpenCheck,
  CheckCircle2,
  Download,
  FileJson,
  FileText,
  Inbox,
  Lightbulb,
  Library,
  Loader2,
  MessageSquareText,
  Plus,
  RefreshCw,
  Send,
  Trash2,
  WifiOff,
  X,
} from 'lucide-react'
import toast from 'react-hot-toast'
import logo from '@/assets/icon.png'
import { useTaskStore } from '@/store/taskStore'
import { useModelStore } from '@/store/modelStore'
import type { EnabledModel } from '@/services/model'
import { buildWorkspaceSearch } from '@/utils/workspaceNavigation'
import {
  addTopicPaper,
  addTopicEvidence,
  askTopic,
  confirmImport,
  createHandoff,
  createTopic,
  createTopicSynthesis,
  deleteImport,
  deleteTopic,
  getFastNewsCatalog,
  getFastWriteProjects,
  getFastWriteStatus,
  getTopic,
  handoffDownloadUrl,
  importFastInsight,
  importFastNews,
  listHandoffs,
  listImports,
  listTopics,
  removeTopicPaper,
  retryHandoff,
  type FastNewsEntry,
  type FastWriteHandoff,
  type PaperCandidate,
  type ResearchTopic,
  type TopicAnswerSource,
  type TopicSynthesis,
  type TopicSynthesisClaim,
} from '@/services/evidenceHub'
import { cn } from '@/lib/utils'

type Tab = 'inbox' | 'topics' | 'handoffs'

type KnowledgeMessage = {
  role: 'user' | 'assistant'
  content: string
  sources?: TopicAnswerSource[]
}

const roleLabels: Record<string, string> = {
  question: '问题',
  method: '方法',
  experiment: '实验',
  limitation: '局限',
  other: '其他',
}

const evidenceSourceLabels: Record<string, string> = {
  manual: '手工证据',
  annotation: '阅读批注',
  report: '阅读报告',
}

export default function ResearchPage() {
  const navigate = useNavigate()
  const tasks = useTaskStore(state => state.tasks)
  const loadSavedTasks = useTaskStore(state => state.loadSavedTasks)
  const [tab, setTab] = useState<Tab>('topics')
  const [candidates, setCandidates] = useState<PaperCandidate[]>([])
  const [topics, setTopics] = useState<ResearchTopic[]>([])
  const [handoffs, setHandoffs] = useState<FastWriteHandoff[]>([])
  const [busy, setBusy] = useState('')

  const reloadCandidates = async () => setCandidates(await listImports())
  const reloadTopics = async () => setTopics(await listTopics())
  const reloadHandoffs = async () => setHandoffs(await listHandoffs())

  useEffect(() => {
    Promise.allSettled([reloadCandidates(), reloadTopics(), reloadHandoffs()])
  }, [])

  return (
    <div className="h-screen overflow-y-auto bg-slate-100 text-slate-900">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1500px] items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <Link to="/" className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900">
              <ArrowLeft className="h-4 w-4" />资料库
            </Link>
            <span className="h-6 w-px bg-slate-200" />
            <img src={logo} className="h-8 w-8 rounded" alt="FastRead" />
            <div>
              <h1 className="text-base font-semibold">专题知识库</h1>
              <p className="text-[11px] text-slate-400">管理专题论文 · 多篇总结 · 统一提问 · 页码溯源</p>
            </div>
          </div>
          <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs text-blue-700">每条回答只使用当前专题论文</div>
        </div>
        <nav className="mx-auto flex max-w-[1500px] gap-1 px-6">
          <TabButton active={tab === 'topics'} onClick={() => setTab('topics')} icon={Library}>知识库目录</TabButton>
          <TabButton active={tab === 'inbox'} onClick={() => setTab('inbox')} icon={Inbox}>论文候选</TabButton>
          <TabButton active={tab === 'handoffs'} onClick={() => setTab('handoffs')} icon={Send}>FastWrite 交接</TabButton>
        </nav>
      </header>
      <main className="mx-auto max-w-[1500px] p-6">
        {tab === 'inbox' && (
          <InboxPanel
            candidates={candidates}
            reload={reloadCandidates}
            loadTasks={loadSavedTasks}
            navigate={navigate}
            busy={busy}
            setBusy={setBusy}
          />
        )}
        {tab === 'topics' && (
          <TopicsPanel
            topics={topics}
            reload={reloadTopics}
            tasks={tasks}
            navigate={navigate}
            busy={busy}
            setBusy={setBusy}
          />
        )}
        {tab === 'handoffs' && (
          <HandoffsPanel
            handoffs={handoffs}
            reload={reloadHandoffs}
            topics={topics}
            tasks={tasks}
            busy={busy}
            setBusy={setBusy}
          />
        )}
      </main>
    </div>
  )
}

function TabButton({ active, onClick, icon: Icon, children }: { active: boolean; onClick: () => void; icon: typeof Inbox; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className={cn('inline-flex h-11 items-center gap-2 border-b-2 px-4 text-sm font-medium', active ? 'border-blue-700 text-blue-800' : 'border-transparent text-slate-500 hover:text-slate-900')}>
      <Icon className="h-4 w-4" />{children}
    </button>
  )
}

function InboxPanel({ candidates, reload, loadTasks, navigate, busy, setBusy }: any) {
  const [catalog, setCatalog] = useState<FastNewsEntry[]>([])
  const [catalogMeta, setCatalogMeta] = useState<{ commit?: string; stale?: boolean; updated_at?: string; warning?: string }>({})
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [fastInsight, setFastInsight] = useState('')
  const [query, setQuery] = useState('')
  const [producer, setProducer] = useState('')
  const [status, setStatus] = useState('')
  const [venue, setVenue] = useState('')
  const [year, setYear] = useState('')
  const [category, setCategory] = useState('')
  const filtered = useMemo(() => candidates.filter((item: PaperCandidate) => {
    const haystack = `${item.title} ${item.venue} ${item.authors.join(' ')}`.toLowerCase()
    return (!query || haystack.includes(query.toLowerCase()))
      && (!producer || item.producer === producer)
      && (!status || item.import_status === status)
      && (!venue || item.venue.toLowerCase().includes(venue.toLowerCase()))
      && (!year || String(item.year || '') === year)
      && (!category || (item.categories || []).some(value => value.toLowerCase().includes(category.toLowerCase())))
  }), [candidates, category, producer, query, status, venue, year])

  const loadCatalog = async (refresh = false) => {
    setBusy('catalog')
    try {
      const result = await getFastNewsCatalog({ limit: 300, refresh })
      setCatalog(result.entries)
      setCatalogMeta(result)
    }
    finally { setBusy('') }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[390px_minmax(0,1fr)]">
      <aside className="space-y-4">
        <Panel title="FastNews 公开论文目录" subtitle="只读取 FastR-D/FastNews 固定 JSONL；commit 与缓存状态可审计。">
          <div className="flex gap-2">
            <button type="button" onClick={() => loadCatalog(Boolean(catalog.length))} className="primary-button" disabled={busy === 'catalog'}>
              {busy === 'catalog' ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {catalog.length ? '检查更新' : '读取目录'}
            </button>
            {selected.size > 0 && (
              <button type="button" className="secondary-button" onClick={async () => {
                setBusy('fastnews-import')
                try { await importFastNews([...selected]); await reload(); setSelected(new Set()); toast.success('候选已进入收件箱') }
                finally { setBusy('') }
              }}>导入 {selected.size} 项</button>
            )}
          </div>
          {catalogMeta.commit && <p className="mt-2 break-all font-mono text-[10px] text-slate-400">commit {catalogMeta.commit}{catalogMeta.stale ? ' · 离线缓存' : ' · 当前目录'}</p>}
          {catalogMeta.warning && <p className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-800">{catalogMeta.warning}</p>}
          <div className="mt-3 max-h-[370px] space-y-2 overflow-y-auto">
            {catalog.map(item => (
              <label key={item.catalog_id} className="flex cursor-pointer gap-2 rounded-md border border-slate-200 p-2.5 hover:border-blue-300">
                <input type="checkbox" checked={selected.has(item.catalog_id)} onChange={event => setSelected(current => {
                  const next = new Set(current)
                  if (event.target.checked) next.add(item.catalog_id)
                  else next.delete(item.catalog_id)
                  return next
                })} />
                <span className="min-w-0">
                  <span className="block text-xs font-medium leading-5">{item.title}</span>
                  <span className="block truncate text-[10px] text-slate-400">{item.venue}{item.year ? ` · ${item.year}` : ''}</span>
                </span>
              </label>
            ))}
            {!catalog.length && <Empty text="尚未读取 FastNews 目录" />}
          </div>
        </Panel>
        <Panel title="FastInsight JSON" subtitle="接受 verify_paper.py 输出、best 对象或扁平论文 JSON；最多 1 MiB，不执行内容。">
          <textarea value={fastInsight} onChange={event => setFastInsight(event.target.value)} className="min-h-40 w-full rounded-md border border-slate-200 p-3 font-mono text-xs" placeholder='粘贴 {"best": {...}}' />
          <button type="button" className="primary-button mt-2" disabled={!fastInsight.trim() || busy === 'fastinsight'} onClick={async () => {
            setBusy('fastinsight')
            try { await importFastInsight(fastInsight); await reload(); setFastInsight(''); toast.success('FastInsight 候选已导入') }
            finally { setBusy('') }
          }}><FileJson className="h-4 w-4" />导入 JSON</button>
        </Panel>
      </aside>
      <Panel title="候选收件箱" subtitle="上游元数据始终标为发现线索；只有重新抓取和锁定原文后才成为论文任务。">
        <div className="mb-4 grid gap-2 md:grid-cols-3 xl:grid-cols-6">
          <input className="field" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索标题、作者、会议" />
          <select className="field" value={producer} onChange={event => setProducer(event.target.value)}><option value="">全部来源</option><option value="fastnews">FastNews</option><option value="fastinsight">FastInsight</option></select>
          <input className="field" value={venue} onChange={event => setVenue(event.target.value)} placeholder="会议筛选" />
          <input className="field" value={year} onChange={event => setYear(event.target.value)} placeholder="年份" inputMode="numeric" />
          <input className="field" value={category} onChange={event => setCategory(event.target.value)} placeholder="分类" />
          <select className="field" value={status} onChange={event => setStatus(event.target.value)}><option value="">全部状态</option><option value="pending">待确认</option><option value="imported">已导入</option></select>
        </div>
        <div className="space-y-3">
          {filtered.map((item: PaperCandidate) => (
            <article key={item.id} className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-800">{item.discovery_status}</span>
                    <span className={cn('rounded px-2 py-0.5 text-[10px] font-medium', item.task_id ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500')}>{item.source_lock_status}</span>
                    <span className="font-mono text-[10px] uppercase text-slate-400">{item.producer}</span>
                  </div>
                  <h3 className="mt-2 text-sm font-semibold leading-6">{item.title}</h3>
                  <p className="mt-1 text-xs text-slate-500">{item.authors.slice(0, 5).join('、') || '作者未提供'} · {item.venue || 'venue 未提供'} {item.year || ''}</p>
                  <p className="mt-2 line-clamp-3 text-xs leading-5 text-slate-500">{item.abstract || '摘要未提供'}</p>
                  {item.source_commit && <p className="mt-2 font-mono text-[9px] text-slate-400">source commit {item.source_commit.slice(0, 12)}</p>}
                </div>
                <div className="flex shrink-0 gap-2">
                  {item.task_id ? (
                    <button type="button" className="secondary-button" onClick={() => navigate(`/workspace?${buildWorkspaceSearch({ taskId: item.task_id || undefined, view: 'source' })}`)}><FileText className="h-4 w-4" />打开原文</button>
                  ) : (
                    <button type="button" className="primary-button" disabled={busy === item.id} onClick={async () => {
                      setBusy(item.id)
                      try {
                        const imported = await confirmImport(item.id); await reload(); await loadTasks(); toast.success('原文已锁定')
                        if (imported.task_id) navigate(`/workspace?${buildWorkspaceSearch({ taskId: imported.task_id, view: 'source' })}`)
                      }
                      finally { setBusy('') }
                    }}>{busy === item.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArchiveRestore className="h-4 w-4" />}确认并导入</button>
                  )}
                  <button type="button" className="icon-button" title="删除候选" onClick={async () => { await deleteImport(item.id); await reload() }}><Trash2 className="h-4 w-4" /></button>
                </div>
              </div>
            </article>
          ))}
          {!filtered.length && <Empty text="收件箱为空" />}
        </div>
      </Panel>
    </div>
  )
}

function TopicsPanel({ topics, reload, tasks, navigate, busy, setBusy }: any) {
  const [question, setQuestion] = useState('')
  const [scope, setScope] = useState('')
  const [hypotheses, setHypotheses] = useState('')
  const [selectedId, setSelectedId] = useState<string>('')
  const [topic, setTopic] = useState<ResearchTopic | null>(null)
  const [synthesis, setSynthesis] = useState<TopicSynthesis | null>(null)
  const [paperId, setPaperId] = useState('')
  const [evidencePaper, setEvidencePaper] = useState('')
  const [evidencePage, setEvidencePage] = useState('1')
  const [evidenceQuote, setEvidenceQuote] = useState('')
  const [evidenceNote, setEvidenceNote] = useState('')
  const [evidenceRole, setEvidenceRole] = useState<'question' | 'method' | 'experiment' | 'limitation' | 'other'>('other')
  const [knowledgeInput, setKnowledgeInput] = useState('')
  const [knowledgeMessages, setKnowledgeMessages] = useState<KnowledgeMessage[]>([])
  const [selectedModelId, setSelectedModelId] = useState('')
  const modelList = useModelStore(state => state.modelList)
  const loadEnabledModels = useModelStore(state => state.loadEnabledModels)
  const model = useMemo(
    () => modelList.find(item => String(item.id) === selectedModelId) || modelList[0],
    [modelList, selectedModelId],
  )

  useEffect(() => {
    if (!modelList.length) loadEnabledModels()
  }, [loadEnabledModels, modelList.length])

  const loadTopic = async (id: string, resetChat = true) => {
    setSelectedId(id)
    setTopic(await getTopic(id))
    setSynthesis(null)
    if (resetChat) setKnowledgeMessages([])
  }

  const runKnowledgeQuery = async (mode: 'question' | 'summary') => {
    if (!topic) return
    const question = mode === 'question' ? knowledgeInput.trim() : ''
    if (mode === 'question' && !question) return
    if (!model?.provider_id || !model?.model_name) {
      toast.error('专题总结与提问需要模型，请先在设置中启用一个模型')
      return
    }
    const history = knowledgeMessages.map(message => ({ role: message.role, content: message.content }))
    if (question) {
      setKnowledgeMessages(current => [...current, { role: 'user', content: question }])
      setKnowledgeInput('')
    }
    setBusy(mode === 'summary' ? 'topic-summary' : 'topic-chat')
    try {
      const result = await askTopic(topic.id, {
        question,
        history,
        provider_id: model.provider_id,
        model_name: model.model_name,
        mode,
      })
      setKnowledgeMessages(current => [...current, {
        role: 'assistant',
        content: result.answer,
        sources: result.sources,
      }])
    }
    finally {
      setBusy('')
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[330px_minmax(0,1fr)]">
      <aside className="space-y-4">
        <Panel title="新建专题知识库" subtitle="例如：越狱攻击、大模型安全、软件供应链安全。">
          <input className="field" value={question} onChange={event => setQuestion(event.target.value)} placeholder="专题名称" />
          <textarea className="field mt-2 min-h-20" value={scope} onChange={event => setScope(event.target.value)} placeholder="关注范围与研究问题" />
          <textarea className="field mt-2 min-h-20" value={hypotheses} onChange={event => setHypotheses(event.target.value)} placeholder="待验证想法（可选，每行一条）" />
          <button type="button" className="primary-button mt-2" disabled={!question.trim()} onClick={async () => {
            const created = await createTopic({ question, scope_statement: scope, user_hypotheses: hypotheses.split('\n').map((item: string) => item.trim()).filter(Boolean) })
            setQuestion(''); setScope(''); setHypotheses(''); await reload(); await loadTopic(created.id)
          }}><Plus className="h-4 w-4" />创建知识库</button>
        </Panel>
        <Panel title="知识库目录" subtitle={`${topics.length} 个专题知识库`}>
          <div className="space-y-2">
            {topics.map((item: ResearchTopic) => (
              <button key={item.id} type="button" onClick={() => loadTopic(item.id)} className={cn('w-full rounded-md border p-3 text-left', selectedId === item.id ? 'border-blue-400 bg-blue-50' : 'border-slate-200 hover:bg-slate-50')}>
                <span className="block text-xs font-semibold leading-5">{item.question}</span>
                <span className="mt-1 block text-[10px] text-slate-400">{item.paper_count || 0} 篇论文 · {item.evidence_count || 0} 条证据</span>
              </button>
            ))}
            {!topics.length && <Empty text="尚无专题知识库" />}
          </div>
        </Panel>
      </aside>
      <Panel title={topic?.question || '专题知识库'} subtitle={topic ? topic.scope_statement || '尚未填写关注范围' : '选择或创建一个专题知识库'}>
        {!topic ? <Empty text="请从左侧选择知识库" /> : (
          <div className="space-y-6">
            <section className="rounded-lg border border-slate-200 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">论文管理</h3>
                  <p className="mt-1 text-xs text-slate-500">本知识库当前包含 {topic.papers?.length || 0} 篇论文。</p>
                </div>
                <button type="button" className="icon-button text-red-500" title="删除整个知识库" onClick={async () => { if (window.confirm('删除知识库及其论文关系、证据和综合产物？')) { await deleteTopic(topic.id); setTopic(null); setSelectedId(''); await reload() } }}><Trash2 className="h-4 w-4" /></button>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <select className="field min-w-64 flex-1" value={paperId} onChange={event => setPaperId(event.target.value)}>
                  <option value="">选择论文加入专题</option>
                  {tasks.filter((task: any) => !(topic.papers || []).some(link => link.task_id === task.id)).map((task: any) => <option key={task.id} value={task.id}>{task.title || task.paperDocument?.title || task.id}</option>)}
                </select>
                <button type="button" className="secondary-button" disabled={!paperId} onClick={async () => { await addTopicPaper(topic.id, paperId); setPaperId(''); await loadTopic(topic.id); await reload() }}><Plus className="h-4 w-4" />加入论文</button>
                <button type="button" className="secondary-button" disabled={busy === 'synthesis' || !model || (topic.papers?.length || 0) < 2} onClick={async () => {
                  if (!model) return
                  setBusy('synthesis')
                  try {
                    const result = await createTopicSynthesis(topic.id, {
                      provider_id: model.provider_id,
                      model_name: model.model_name,
                    })
                    setSynthesis(result)
                    await loadTopic(topic.id, false)
                    setSynthesis(result)
                  }
                  finally { setBusy('') }
                }}>{busy === 'synthesis' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Lightbulb className="h-4 w-4" />}生成跨论文综合</button>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {(topic.papers || []).map(link => (
                  <div key={link.task_id} className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                    <BookOpenCheck className="h-4 w-4 shrink-0 text-blue-700" />
                    <button type="button" className="min-w-0 flex-1 truncate text-left text-xs font-medium text-slate-700 hover:text-blue-700" onClick={() => navigate(`/workspace?${buildWorkspaceSearch({ taskId: link.task_id, view: 'source' })}`)}>{link.title || link.task_id}</button>
                    <button type="button" title="从知识库移除" className="text-slate-400 hover:text-red-600" onClick={async () => {
                      if (!window.confirm(`从“${topic.question}”移除这篇论文？`)) return
                      await removeTopicPaper(topic.id, link.task_id)
                      await loadTopic(topic.id)
                      await reload()
                    }}><X className="h-3.5 w-3.5" /></button>
                  </div>
                ))}
                {!(topic.papers || []).length && <div className="sm:col-span-2 xl:col-span-3"><Empty text="请先从上方选择已导入论文加入知识库" /></div>}
              </div>
            </section>
            <KnowledgeBaseChat
              topic={topic}
              messages={knowledgeMessages}
              input={knowledgeInput}
              setInput={setKnowledgeInput}
              busy={busy}
              models={modelList}
              selectedModelId={model ? String(model.id) : ''}
              onModelChange={setSelectedModelId}
              onAsk={() => runKnowledgeQuery('question')}
              onSummary={() => runKnowledgeQuery('summary')}
              navigate={navigate}
            />
            <section className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <h3 className="text-xs font-semibold text-slate-700">手工补充逐字证据</h3>
              <p className="mt-1 text-[10px] text-slate-400">即使没有模型也可建立矩阵；服务端会逐字核对页码和原文。</p>
              <div className="mt-3 grid gap-2 md:grid-cols-[minmax(0,1fr)_90px_130px]">
                <select className="field" value={evidencePaper} onChange={event => setEvidencePaper(event.target.value)}><option value="">选择专题论文</option>{(topic.papers || []).map(link => <option key={link.task_id} value={link.task_id}>{link.title || link.task_id}</option>)}</select>
                <input className="field" type="number" min={1} value={evidencePage} onChange={event => setEvidencePage(event.target.value)} placeholder="页码" />
                <select className="field" value={evidenceRole} onChange={event => setEvidenceRole(event.target.value as typeof evidenceRole)}>{Object.entries(roleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
              </div>
              <textarea className="field mt-2 min-h-20" value={evidenceQuote} onChange={event => setEvidenceQuote(event.target.value)} placeholder="粘贴指定页中的逐字原文" />
              <input className="field mt-2" value={evidenceNote} onChange={event => setEvidenceNote(event.target.value)} placeholder="用户备注（不会混入论文主张）" />
              <button type="button" className="secondary-button mt-2" disabled={!evidencePaper || !evidenceQuote.trim()} onClick={async () => {
                await addTopicEvidence(topic.id, { task_id: evidencePaper, page: Number(evidencePage), exact_quote: evidenceQuote, user_note: evidenceNote, role: evidenceRole })
                setEvidenceQuote(''); setEvidenceNote(''); await loadTopic(topic.id)
              }}><Plus className="h-4 w-4" />核对并加入矩阵</button>
            </section>
            <section className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
              <div className="flex flex-wrap items-end justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">证据矩阵</h3>
                  <p className="mt-1 text-xs leading-5 text-slate-500">按研究职责整理已通过页码和逐字引文校验的证据；空缺会保留，不由模型补写。</p>
                </div>
                <span className="rounded bg-white px-2 py-1 text-[10px] text-slate-500">{topic.evidence_items?.length || 0} 条已校验证据</span>
              </div>
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                {Object.entries(roleLabels).map(([role, label]) => {
                  const items = topic.evidence_matrix?.[role] || []
                  return (
                    <div key={role} className="rounded-lg border border-slate-200 bg-white p-3">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-xs font-semibold text-slate-800">{label}</div>
                        <span className="font-mono text-[10px] text-slate-400">{items.length}</span>
                      </div>
                      <div className="mt-2 space-y-2">
                        {items.map(item => {
                          const paperTitle = topic.papers?.find(paper => paper.task_id === item.task_id)?.title || item.task_id
                          return (
                            <button key={item.id} type="button" className="block w-full rounded-md border border-slate-200 bg-slate-50 p-3 text-left transition hover:border-blue-300 hover:bg-blue-50/50" onClick={() => navigate(`/workspace?${buildWorkspaceSearch({ taskId: item.task_id, view: 'source', page: item.page, quote: item.exact_quote })}`)}>
                              <span className="flex items-center justify-between gap-3 text-[10px] text-slate-500">
                                <span className="min-w-0 truncate font-medium text-slate-700">{paperTitle}</span>
                                <span className="shrink-0 font-mono text-blue-700">第 {item.page} 页</span>
                              </span>
                              <span className="mt-2 line-clamp-3 block text-xs leading-5 text-slate-700">“{item.exact_quote}”</span>
                              <span className="mt-2 block text-[10px] text-slate-400">{evidenceSourceLabels[item.source_kind] || item.source_kind}</span>
                            </button>
                          )
                        })}
                        {!items.length && <p className="rounded border border-dashed border-slate-200 py-5 text-center text-[10px] text-slate-400">该维度暂无逐字证据</p>}
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
            <section className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <h3 className="text-xs font-semibold text-amber-900">用户假设（不计入论文共同报告）</h3>
              <ul className="mt-2 list-disc pl-5 text-xs leading-5 text-amber-900">{topic.user_hypotheses.map(item => <li key={item}>{item}</li>)}{!topic.user_hypotheses.length && <li className="list-none text-amber-700">未填写</li>}</ul>
            </section>
            {synthesis && <SynthesisView synthesis={synthesis} navigate={navigate} />}
          </div>
        )}
      </Panel>
    </div>
  )
}

function KnowledgeBaseChat({
  topic,
  messages,
  input,
  setInput,
  busy,
  models,
  selectedModelId,
  onModelChange,
  onAsk,
  onSummary,
  navigate,
}: {
  topic: ResearchTopic
  messages: KnowledgeMessage[]
  input: string
  setInput: (value: string) => void
  busy: string
  models: EnabledModel[]
  selectedModelId: string
  onModelChange: (modelId: string) => void
  onAsk: () => void
  onSummary: () => void
  navigate: ReturnType<typeof useNavigate>
}) {
  const running = busy === 'topic-chat' || busy === 'topic-summary'
  const canQuery = Boolean(topic.papers?.length && selectedModelId)
  return (
    <section className="overflow-hidden rounded-xl border border-blue-200 bg-white shadow-sm">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-blue-100 bg-blue-50/60 px-5 py-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-blue-950">
            <MessageSquareText className="h-4 w-4" />
            多篇论文总结与提问
          </div>
          <p className="mt-1 text-xs leading-5 text-blue-800">只检索“{topic.question}”中的论文；答案来源可回跳到具体页码。</p>
        </div>
        <div className="flex items-center gap-2">
          {models.length
            ? <select
                aria-label="专题知识库使用模型"
                className="h-9 max-w-64 rounded-md border border-blue-200 bg-white px-2 font-mono text-xs text-slate-600"
                value={selectedModelId}
                onChange={event => onModelChange(event.target.value)}
                disabled={running}
              >
                {models.map(model => (
                  <option key={String(model.id)} value={String(model.id)}>{model.model_name} · {model.provider_id}</option>
                ))}
              </select>
            : <Link to="/settings/model" className="text-xs font-medium text-amber-700 hover:underline">先启用模型</Link>}
          <button type="button" className="primary-button" disabled={!canQuery || running} onClick={onSummary}>
            {busy === 'topic-summary' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Library className="h-4 w-4" />}
            一键总结知识库
          </button>
        </div>
      </header>

      <div className="max-h-[520px] min-h-56 space-y-4 overflow-y-auto px-5 py-5">
        {!messages.length && (
          <div className="flex min-h-44 flex-col items-center justify-center text-center">
            <Library className="h-8 w-8 text-blue-200" />
            <p className="mt-3 text-sm font-medium text-slate-700">先生成专题总览，或直接提出一个跨论文问题</p>
            <p className="mt-1 max-w-xl text-xs leading-5 text-slate-500">例如：这些论文的攻击假设有什么差异？各自用了什么评估指标？哪些结论互相冲突？</p>
          </div>
        )}
        {messages.map((message, index) => (
          <article key={`${message.role}-${index}`} className={message.role === 'user' ? 'ml-auto max-w-3xl rounded-lg bg-slate-900 px-4 py-3 text-sm text-white' : 'max-w-4xl rounded-lg border border-slate-200 bg-slate-50 px-4 py-4'}>
            {message.role === 'user' ? message.content : (
              <>
                <div className="prose prose-sm max-w-none prose-p:my-2 prose-li:my-1">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                </div>
                {message.sources && message.sources.length > 0 && (
                  <div className="mt-4 border-t border-slate-200 pt-3">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">原文来源</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {message.sources.map(source => (
                        <button
                          key={`${source.source_id}-${source.task_id}-${source.page_start}`}
                          type="button"
                          title={source.exact_quote}
                          onClick={() => navigate(`/workspace?${buildWorkspaceSearch({ taskId: source.task_id, view: 'source', page: source.page_start, quote: source.exact_quote })}`)}
                          className="rounded-md border border-blue-200 bg-white px-2.5 py-1.5 text-left text-[11px] text-blue-800 transition hover:bg-blue-50"
                        >
                          <span className="font-mono font-semibold">[{source.source_id}]</span> {source.title} · 第 {source.page_start} 页
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </article>
        ))}
        {running && (
          <div className="flex items-center gap-2 text-xs text-blue-700"><Loader2 className="h-4 w-4 animate-spin" />正在阅读专题中的多篇论文并核对页码…</div>
        )}
      </div>

      <div className="border-t border-slate-200 bg-white p-4">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={event => setInput(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                onAsk()
              }
            }}
            className="field min-h-11 flex-1 resize-none py-3"
            placeholder="针对这个知识库提问；Enter 发送，Shift + Enter 换行"
          />
          <button type="button" className="primary-button self-stretch px-4" disabled={!canQuery || !input.trim() || running} onClick={onAsk}>
            {busy === 'topic-chat' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            提问
          </button>
        </div>
      </div>
    </section>
  )
}

function SynthesisView({ synthesis, navigate }: { synthesis: TopicSynthesis; navigate: ReturnType<typeof useNavigate> }) {
  const sections = [
    ['多篇论文共同报告（非领域共识）', synthesis.common_reports],
    ['差异', synthesis.differences],
    ['冲突', synthesis.conflicts],
  ] as const
  return (
    <section className="rounded-xl border border-blue-200 bg-blue-50/40 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-blue-950">Idea 可行性与跨论文综合</h3>
          <p className="mt-1 text-xs leading-5 text-blue-800">模型只归纳已编号证据；页码、逐字引文和论文成员关系由程序复核。</p>
        </div>
        {synthesis.model && <span className="rounded bg-white px-2 py-1 font-mono text-[10px] text-slate-500">{synthesis.model.model_name} · {synthesis.model.provider_id}</span>}
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {sections.map(([label, entries]) => (
          <div key={label} className="rounded-lg border border-blue-100 bg-white/70 p-3">
            <h4 className="text-xs font-semibold text-blue-900">{label}</h4>
            <SynthesisClaimList claims={entries} navigate={navigate} empty="现有逐字证据不足以确认" />
          </div>
        ))}
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h4 className="text-xs font-semibold text-slate-800">问题与现有进展</h4>
          <p className="mt-2 text-xs leading-6 text-slate-700">{synthesis.idea_feasibility.problem || synthesis.question}</p>
          <SynthesisClaimList claims={synthesis.idea_feasibility.what_papers_achieved} navigate={navigate} empty="现有论文进展尚未形成可核验归纳" />
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h4 className="text-xs font-semibold text-slate-800">关键反例与局限</h4>
          <SynthesisClaimList claims={synthesis.idea_feasibility.counterexamples_and_limitations} navigate={navigate} empty="现有证据尚未提供明确反例或局限" />
        </div>
        <FeasibilityText label="建议的最小验证实验" value={synthesis.idea_feasibility.minimum_validation_experiment} />
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h4 className="text-xs font-semibold text-slate-800">证据边界</h4>
          <TextList label="尚未被支持的用户假设" values={synthesis.idea_feasibility.unsupported_hypotheses} />
          <TextList label="仍需补读" values={[...synthesis.idea_feasibility.evidence_to_read, ...synthesis.evidence_gaps]} />
        </div>
      </div>
    </section>
  )
}

function SynthesisClaimList({ claims, navigate, empty }: { claims: TopicSynthesisClaim[]; navigate: ReturnType<typeof useNavigate>; empty: string }) {
  if (!claims.length) return <p className="mt-3 text-xs leading-5 text-slate-400">{empty}</p>
  return (
    <div className="mt-3 space-y-3">
      {claims.map((claim, index) => (
        <article key={`${claim.statement}-${index}`} className="border-t border-slate-100 pt-3 first:border-0 first:pt-0">
          <p className="text-xs leading-6 text-slate-700">{claim.statement}</p>
          <div className="mt-2 flex flex-wrap gap-1">
            {claim.citations.map(citation => (
              <button key={`${citation.task_id}-${citation.page}-${citation.exact_quote}`} type="button" title={citation.exact_quote} onClick={() => navigate(`/workspace?${buildWorkspaceSearch({ taskId: citation.task_id, view: 'source', page: citation.page, quote: citation.exact_quote })}`)} className="rounded bg-blue-100 px-2 py-1 font-mono text-[10px] text-blue-800 hover:bg-blue-200">第 {citation.page} 页</button>
            ))}
          </div>
        </article>
      ))}
    </div>
  )
}

function FeasibilityText({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg border border-slate-200 bg-white p-4"><h4 className="text-xs font-semibold text-slate-800">{label}</h4><p className="mt-2 whitespace-pre-wrap text-xs leading-6 text-slate-700">{value || '证据不足，保留空缺'}</p></div>
}

function TextList({ label, values }: { label: string; values: string[] }) {
  const unique = [...new Set(values.filter(Boolean))]
  return <div className="mt-3"><div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</div>{unique.length ? <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-5 text-slate-700">{unique.map(item => <li key={item}>{item}</li>)}</ul> : <p className="mt-1 text-xs text-slate-400">无</p>}</div>
}

function HandoffsPanel({ handoffs, reload, topics, tasks, busy, setBusy }: any) {
  const [status, setStatus] = useState<{ enabled: boolean; available: boolean; origin: string; message?: string } | null>(null)
  const [projects, setProjects] = useState<Array<{ id?: string; projectId?: string; name?: string }>>([])
  const [projectId, setProjectId] = useState('')
  const [source, setSource] = useState('')
  const [includeNotes, setIncludeNotes] = useState(false)

  useEffect(() => {
    getFastWriteStatus().then(async result => {
      setStatus(result)
      if (result.available) setProjects(await getFastWriteProjects())
    }).catch(() => setStatus({ enabled: true, available: false, origin: '', message: 'FastWrite 状态读取失败' }))
  }, [])

  const submit = async () => {
    if (!projectId || !source) return
    setBusy('handoff')
    try {
      const [kind, id] = source.split(':', 2)
      const receipt = await createHandoff({ project_id: projectId, task_id: kind === 'task' ? id : undefined, topic_id: kind === 'topic' ? id : undefined, include_user_notes: includeNotes })
      await reload()
      if (receipt.status === 'completed') toast.success('证据包已交接 FastWrite')
      else toast.error('FastWrite 不可用或写入未完成，可下载 ZIP 兜底')
    }
    finally { setBusy('') }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[390px_minmax(0,1fr)]">
      <Panel title="新建不可变交接" subtitle="唯一目录、逐文件创建、manifest 最后写入；不覆盖任何 FastWrite 文件。">
        <div className={cn('mb-4 rounded-md border p-3 text-xs', status?.available ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-900')}>
          {status?.available ? <span className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4" />FastWrite 已连接 · {status.origin}</span> : <span className="flex items-center gap-2"><WifiOff className="h-4 w-4" />{status?.message || '检查 FastWrite 中…'}</span>}
        </div>
        <label className="label">目标项目</label>
        {projects.length ? (
          <select className="field" value={projectId} onChange={event => setProjectId(event.target.value)}><option value="">选择 FastWrite 项目</option>{projects.map(item => { const id = String(item.id || item.projectId || ''); return <option key={id} value={id}>{item.name || id}</option> })}</select>
        ) : (
          <input className="field" value={projectId} onChange={event => setProjectId(event.target.value)} placeholder="离线时填写目标 project_id 以生成回执" />
        )}
        <label className="label mt-3">证据来源</label>
        <select className="field" value={source} onChange={event => setSource(event.target.value)}><option value="">选择单篇论文或专题</option><optgroup label="专题">{topics.map((item: ResearchTopic) => <option key={item.id} value={`topic:${item.id}`}>{item.question}</option>)}</optgroup><optgroup label="单篇论文">{tasks.map((task: any) => <option key={task.id} value={`task:${task.id}`}>{task.title || task.paperDocument?.title || task.id}</option>)}</optgroup></select>
        <label className="mt-3 flex items-center gap-2 text-xs text-slate-600"><input type="checkbox" checked={includeNotes} onChange={event => setIncludeNotes(event.target.checked)} />显式包含 user-notes.md（个人总结、批注与用户假设）</label>
        <button type="button" onClick={submit} disabled={!projectId || !source || busy === 'handoff'} className="primary-button mt-4"><Send className="h-4 w-4" />{status?.available ? '生成并交接' : '生成本地证据包'}</button>
        {!status?.available && <p className="mt-3 text-xs leading-5 text-slate-500">FastWrite 不可用时，可从已有失败回执下载内容完全相同的 ZIP / Markdown / BibTeX / JSON。</p>}
      </Panel>
      <Panel title="交接回执" subtitle="重复提交同一 bundle 和项目返回已有回执；失败重试只补缺失文件。">
        <div className="space-y-3">
          {handoffs.map((item: FastWriteHandoff) => (
            <article key={item.id} className="rounded-lg border border-slate-200 p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2"><span className={cn('rounded px-2 py-0.5 text-[10px] font-semibold uppercase', item.status === 'completed' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-800')}>{item.status}</span><span className="font-mono text-[10px] text-slate-400">{item.bundle_id}</span></div>
                  <p className="mt-2 text-xs font-medium">{item.target_path}</p>
                  <p className="mt-1 text-[10px] text-slate-400">项目 {item.project_id} · {item.successful_files.length}/{item.files.length} 文件 · manifest {item.manifest_hash.slice(0, 12)}</p>
                  {item.error && <p className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-900">{item.error}</p>}
                </div>
                <div className="flex flex-wrap justify-end gap-1">
                  {item.status !== 'completed' && <button type="button" className="secondary-button" onClick={async () => { await retryHandoff(item.id); await reload() }}><RefreshCw className="h-4 w-4" />重试</button>}
                  {(['zip', 'markdown', 'bibtex', 'json'] as const).map(format => <a key={format} href={handoffDownloadUrl(item.id, format)} className="icon-button" title={`下载 ${format}`}><Download className="h-4 w-4" /><span className="sr-only">{format}</span></a>)}
                </div>
              </div>
            </article>
          ))}
          {!handoffs.length && <Empty text="尚无交接回执" />}
        </div>
      </Panel>
    </div>
  )
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><h2 className="text-sm font-semibold">{title}</h2><p className="mt-1 mb-4 text-xs leading-5 text-slate-500">{subtitle}</p>{children}</section>
}

function Empty({ text }: { text: string }) {
  return <div className="rounded-md border border-dashed border-slate-200 px-4 py-8 text-center text-xs text-slate-400">{text}</div>
}
