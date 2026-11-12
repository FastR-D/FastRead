import {
  Button,
  Checkbox,
  InspectorSection,
  PanelHeader,
  Section,
  Select,
  TextArea,
  TextField,
  Toolbar,
  ListRow,
  StatusBar,
} from '@fastrd/ui-react'
import { API_BASE } from './urls'
import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from './Markdown'
import {
  FileText,
  Plus,
  MessageSquare,
  StickyNote,
  ArrowLeft,
  Check,
  Network,
  BookOpen,
  Files,
} from 'lucide-react'
import PdfReader from './PdfReader'
import Neighbors from './Neighbors'
import { PaperTools } from './Knowledge'
import { AppDialog, WorkbenchSidebar, WorkspaceTabs } from './Chrome'
type Row = Record<string, any>
export default function NotebookDesk({
  target,
  api,
  action,
  jobs,
  providerId,
  model,
  onHome,
  onExternal,
}: Row) {
  const scope = target.book_id ? 'book' : 'paper',
    scopeId = target.book_id || target.paper_id
  const { paper_id: targetPaperId, page: targetPage, version: targetVersion } = target
  const [book, setBook] = useState<Row | null>(null),
    [sources, setSources] = useState<Row[]>([])
  const [checked, setChecked] = useState<string[]>([]),
    [filter, setFilter] = useState('')
  const [paper, setPaper] = useState<Row | null>(null),
    [page, setPage] = useState(target.page || 1),
    [version, setVersion] = useState('')
  const [summary, setSummary] = useState(''),
    [pane, setPane] = useState('chat')
  const [conversation, setConversation] = useState(''),
    [messages, setMessages] = useState<Row[]>([])
  const [quote, setQuote] = useState<Row | null>(null),
    [citation, setCitation] = useState<Row | null>(null)
  const draftKey = `desk-question:${scope}:${scopeId}`
  const [question, setQuestion] = useState(() => localStorage.getItem(draftKey) || '')
  const [notes, setNotes] = useState<Row[]>([]),
    [noteId, setNoteId] = useState(''),
    [noteTitle, setNoteTitle] = useState(''),
    [noteText, setNoteText] = useState('')
  const [notice, setNotice] = useState(''),
    [busy, setBusy] = useState(false),
    [report, setReport] = useState<Row | null>(null)
  const [adding, setAdding] = useState(false),
    [library, setLibrary] = useState<Row[]>([]),
    [url, setUrl] = useState('')
  const [allBooks, setAllBooks] = useState<Row[]>([]),
    [neighborTag, setNeighborTag] = useState(''),
    [matrix, setMatrix] = useState(false)
  const generation = useRef(0),
    initial = useRef(true),
    activePaper = useRef('')
  const revision = jobs.map((j: Row) => `${j.id}:${j.state}`).join(',')
  const messagePath =
    scope === 'book'
      ? `/knowledge-bases/${scopeId}/messages`
      : conversation
        ? `/conversations/${conversation}/messages`
        : ''
  const pending = jobs.find(
    (j: Row) =>
      (scope === 'book'
        ? j.kind === 'knowledge_chat' && j.resource_id === scopeId
        : j.kind === 'chat' && j.resource_id === conversation) &&
      ['queued', 'running'].includes(j.state)
  )
  const lastFailure = jobs.find(
    (j: Row) =>
      (scope === 'book'
        ? j.kind === 'knowledge_chat' && j.resource_id === scopeId
        : j.kind === 'chat' && j.resource_id === conversation) &&
      ['failed', 'needs_attention'].includes(j.state)
  )
  const loadNotes = useCallback(async () => {
    setNotes((await api(`/workspace-notes?scope=${scope}&scope_id=${scopeId}`)).items)
  }, [api, scope, scopeId])
  const open = useCallback(
    async (id: string, location?: Row) => {
      const request = ++generation.current
      const p = await api(`/papers/${id}`)
      if (request !== generation.current) return
      if (activePaper.current !== id) setReport(null)
      activePaper.current = id
      setPaper(p)
      setSummary(localStorage.getItem(`notes:${id}`) ?? p.summary)
      localStorage.setItem(`desk-current:${scope}:${scopeId}`, id)
      const v = location?.version_id || location?.document_version_id || p.active_version
      setVersion(v)
      const count =
        p.versions.find((item: Row) => item.id === v)?.page_count || p.metadata.page_count || 1
      setPage(
        Math.max(
          1,
          Math.min(
            count,
            location?.page ||
              location?.page_start ||
              Number(localStorage.getItem(`desk-page:${id}`)) ||
              1
          )
        )
      )
      setCitation(
        location ? { quote: location.quote || location.exact_quote, nonce: Date.now() } : null
      )
    },
    [api, scope, scopeId]
  )
  const loadSources = useCallback(async () => {
    const b = scope === 'book' ? await api(`/knowledge-bases/${scopeId}`) : null
    const list: Row[] = b ? b.papers : [await api(`/papers/${scopeId}`)]
    setBook(b)
    setSources(list)
    const firstLoad = initial.current
    let saved: string[] | null = null
    try {
      const value = JSON.parse(localStorage.getItem(`desk-checked:${scope}:${scopeId}`) || 'null')
      if (Array.isArray(value)) saved = value
    } catch {
      /* A damaged local preference falls back to all sources. */
    }
    setChecked(previous =>
      firstLoad
        ? (saved ?? list.map((p: Row) => p.id)).filter(id => list.some((p: Row) => p.id === id))
        : previous.filter(id => list.some((p: Row) => p.id === id))
    )
    if (initial.current) {
      initial.current = false
      const preferred = targetPaperId || localStorage.getItem(`desk-current:${scope}:${scopeId}`)
      const chosen = list.find((p: Row) => p.id === preferred) || list[0]
      if (chosen)
        await open(
          chosen.id,
          targetVersion || targetPage ? { version_id: targetVersion, page: targetPage } : undefined
        )
    } else if (!activePaper.current && list.length) {
      await open(list[0].id)
    }
  }, [api, scope, scopeId, targetPaperId, targetPage, targetVersion, open])
  useEffect(() => {
    void action(async () => {
      setAllBooks((await api('/knowledge-bases')).items)
      if (scope === 'paper')
        setConversation((await api(`/papers/${scopeId}/conversations`, 'POST')).id)
    })
  }, [action, api, scope, scopeId])
  useEffect(() => {
    void action(loadSources)
    void action(loadNotes)
  }, [action, loadSources, loadNotes, revision])
  useEffect(() => {
    if (!messagePath) return
    let stopped = false
    void action(async () => {
      const data = await api(messagePath)
      if (!stopped) setMessages(data.items)
    })
    return () => {
      stopped = true
    }
  }, [action, api, messagePath, revision])
  const paperId = paper?.id
  const activeVersion = paper?.active_version
  useEffect(() => {
    if (!paperId) return
    let dead = false
    void action(async () => {
      const list = await api(`/papers/${paperId}/reports`)
      const r = list.items.find((r: Row) => r.version_id === activeVersion)
      const value = r ? await api(`/papers/${paperId}/reports/${r.id}`) : null
      if (!dead) setReport(value)
    })
    return () => {
      dead = true
    }
  }, [action, api, revision, paperId, activeVersion])
  useEffect(() => {
    localStorage.setItem(draftKey, question)
  }, [question, draftKey])
  useEffect(() => {
    if (!initial.current)
      localStorage.setItem(`desk-checked:${scope}:${scopeId}`, JSON.stringify(checked))
  }, [checked, scope, scopeId])
  useEffect(() => {
    if (paperId) localStorage.setItem(`desk-page:${paperId}`, String(page))
  }, [paperId, page])
  async function submit(path: string, body?: unknown) {
    const job = await api(path, 'POST', body, crypto.randomUUID())
    setNotice('处理中…')
    return job
  }
  async function locate(ev: Row) {
    await open(ev.paper_id || paper?.id, ev)
  }
  function references(evidence: Row = {}) {
    return evidence.sources?.map((ev: Row, i: number) => (
      <Button
        key={i}
        className="citation-chip h-auto text-left whitespace-normal"
        title={ev.quote || ev.exact_quote}
        onClick={() => void action(() => locate(ev))}
        type="button"
        variant="quiet"
      >
        [{ev.id || `S${i + 1}`}] {ev.title ? ev.title.slice(0, 32) : '原文'} · 第{' '}
        {ev.page || ev.page_start} 页
      </Button>
    ))
  }
  function markdown(content: string, evidence: Row = {}) {
    const refs = evidence.sources || []
    const find = (id: string) =>
      refs.find((r: Row, i: number) => String(r.id || `S${i + 1}`) === id || `S${i + 1}` === id)
    const linked = content.replace(/\[(S?\d+)\]/g, (whole, value) => {
      const id = value.startsWith('S') ? value : `S${value}`
      return find(id) ? `[${value}](#citation-${id})` : whole
    })
    return (
      <ReactMarkdown
        math
        gfm
        components={{
          a: ({ href, children }) => {
            const ev = href?.startsWith('#citation-') ? find(href.slice(10)) : null
            return ev ? (
              <Button
                className="inline-citation inline-flex"
                title={ev.quote || ev.exact_quote}
                onClick={() => void action(() => locate(ev))}
                type="button"
                variant="quiet"
              >
                {children}
              </Button>
            ) : (
              <a href={href} target="_blank" rel="noreferrer" className="fastui-link break-words">
                {children}
              </a>
            )
          },
        }}
      >
        {linked}
      </ReactMarkdown>
    )
  }
  async function saveAnswer(m: Row) {
    await api('/workspace-notes', 'POST', {
      scope,
      scope_id: scopeId,
      source_message_id: m.id,
      title: '回答笔记 · ' + new Date().toLocaleDateString(),
    })
    await loadNotes()
    setNotice('已保存笔记')
  }
  function capture(value: Row) {
    setQuote({ ...value, title: paper?.title })
    setPane('chat')
    setChecked(ids => (ids.includes(value.paper_id) ? ids : [...ids, value.paper_id]))
    window.setTimeout(
      () => window.document.querySelector<HTMLTextAreaElement>('.desk-composer textarea')?.focus(),
      0
    )
  }
  async function send() {
    if (!messagePath || busy || pending || !checked.length) return
    setBusy(true)
    const content = quote
      ? `${question || '请解释这段内容。'}\n\n选中的原文（${String(quote.title || paper?.title).slice(0, 160)}，第 ${quote.page} 页）：\n${String(quote.quote).slice(0, 1500)}`
      : question
    try {
      await submit(messagePath, {
        content,
        provider_id: providerId,
        model,
        ...(scope === 'book' ? { paper_ids: checked } : {}),
      })
      setQuestion('')
      setQuote(null)
      setMessages((await api(messagePath)).items)
    } finally {
      setBusy(false)
    }
  }
  const notebookNotes = (
    <Section className="desk-saved-notes grid gap-3">
      <PanelHeader className="section-heading">
        <h2 className="fastui-heading m-0 text-base">
          {scope === 'book' ? '知识库笔记' : '保存的笔记'}
        </h2>
        <Button
          className="quiet"
          onClick={() => {
            setNoteId('new')
            setNoteTitle('研究笔记')
            setNoteText(localStorage.getItem(`note-draft:${scopeId}`) || '')
          }}
          type="button"
          variant="quiet"
        >
          <Plus size={14} /> 新建
        </Button>
      </PanelHeader>
      {noteId && (
        <form
          onSubmit={e => {
            e.preventDefault()
            void action(async () => {
              if (noteId === 'new')
                await api('/workspace-notes', 'POST', {
                  scope,
                  scope_id: scopeId,
                  title: noteTitle,
                  content: noteText,
                })
              else
                await api(`/workspace-notes/${noteId}`, 'PUT', {
                  title: noteTitle,
                  content: noteText,
                })
              setNoteId('')
              localStorage.removeItem(`note-draft:${scopeId}`)
              await loadNotes()
              setNotice('笔记已保存')
            })
          }}
          className="grid min-w-0 gap-3"
        >
          <TextField
            aria-label="笔记标题"
            required
            value={noteTitle}
            maxLength={120}
            onChange={e => setNoteTitle(e.target.value)}
            className="w-full"
          />
          <TextArea
            aria-label="笔记正文"
            required
            rows={6}
            value={noteText}
            maxLength={30000}
            onChange={e => {
              setNoteText(e.target.value)
              localStorage.setItem(`note-draft:${scopeId}`, e.target.value)
            }}
            className="w-full"
          />
          <Toolbar className="toolbar" label="操作">
            <Button type="submit" variant="primary">
              保存这条笔记
            </Button>
            <Button type="button" className="quiet" onClick={() => setNoteId('')} variant="quiet">
              取消
            </Button>
          </Toolbar>
        </form>
      )}
      {notes.map(n => (
        <InspectorSection className="saved-note min-w-0" key={n.id} label={n.title}>
          {markdown(n.content, n.evidence)}
          <div className="citation-list flex flex-wrap gap-2">{references(n.evidence)}</div>
          <Toolbar className="toolbar" label="操作">
            <Button
              className="quiet"
              onClick={() => {
                setNoteId(n.id)
                setNoteTitle(n.title)
                setNoteText(n.content)
              }}
              type="button"
              variant="quiet"
            >
              编辑
            </Button>
            <Button
              className="quiet"
              onClick={() => {
                if (window.confirm('删除这条笔记？'))
                  void action(async () => {
                    await api(`/workspace-notes/${n.id}`, 'DELETE')
                    await loadNotes()
                  })
              }}
              type="button"
              variant="quiet"
            >
              删除
            </Button>
          </Toolbar>
        </InspectorSection>
      ))}
      {!notes.length && (
        <p className="desk-muted m-0 text-sm leading-relaxed break-words">暂无笔记</p>
      )}
    </Section>
  )
  const chat = (
    <div className="desk-chat flex min-h-0 flex-col gap-4">
      <div className="chat-history grid min-w-0 gap-3">
        {!messages.length && (
          <div className="chat-welcome grid gap-3">
            <MessageSquare size={28} />
            <h2 className="fastui-heading m-0 text-base">向资料提问</h2>
            <div className="suggested-questions grid gap-2">
              {[
                '概括核心问题',
                '解释方法并引用原文',
                ...(sources.length > 1 ? ['比较所选论文'] : ['总结实验结论']),
              ].map(q => (
                <Button
                  className="quiet"
                  key={q}
                  onClick={() => setQuestion(q)}
                  type="button"
                  variant="quiet"
                >
                  {q}
                </Button>
              ))}
            </div>
          </div>
        )}
        {messages.map(m => (
          <article
            className={`desk-message fastui-section grid min-w-0 gap-3 p-4 break-words ${m.role}`}
            key={m.id}
          >
            <b>{m.role === 'user' ? '你' : 'FastRead'}</b>
            {markdown(m.content, m.evidence)}
            <div className="citation-list flex flex-wrap gap-2">{references(m.evidence)}</div>
            {m.role === 'assistant' && (
              <Button
                className="save-answer quiet"
                onClick={() => void action(() => saveAnswer(m))}
                type="button"
                variant="quiet"
              >
                {notes.some(n => n.source_message_id === m.id) ? (
                  <>
                    <Check size={14} /> 已存入笔记
                  </>
                ) : (
                  <>
                    <StickyNote size={14} /> 保存为笔记
                  </>
                )}
              </Button>
            )}
          </article>
        ))}
        {(busy || pending) && <StatusBar>正在结合所选资料回答…</StatusBar>}
        {lastFailure && !pending && (
          <InspectorSection className="answer-failure" label="有一条回答未完成">
            <p className="m-0 leading-relaxed break-words">{lastFailure.error || '请稍后重试。'}</p>
            <Button
              className="quiet"
              onClick={() => {
                const last = [...messages].reverse().find(m => m.role === 'user')
                if (last) setQuestion(last.content)
              }}
              type="button"
              variant="quiet"
            >
              恢复问题
            </Button>
          </InspectorSection>
        )}
      </div>
      <form
        onSubmit={e => {
          e.preventDefault()
          void action(send)
        }}
        className="desk-composer grid min-w-0 gap-3"
      >
        {quote && (
          <blockquote className="fastui-section m-0 max-h-48 overflow-auto p-3 break-words">
            <span>选文 · 第 {quote.page} 页</span>
            <p className="m-0 leading-relaxed break-words">{quote.quote}</p>
            <Button type="button" className="quiet" onClick={() => setQuote(null)} variant="quiet">
              移除选文
            </Button>
          </blockquote>
        )}
        <TextArea
          aria-label="向所选资料提问"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          placeholder={checked.length ? '输入问题，或在 PDF 上选中一段文字…' : '请先勾选左侧资料'}
          maxLength={quote ? 3000 : 5000}
          rows={3}
          className="w-full"
        />
        <div className="composer-footer flex flex-wrap items-center justify-between gap-2">
          <span>参考 {checked.length} 篇资料</span>
          <Button
            disabled={
              !providerId || !checked.length || busy || !!pending || (!question.trim() && !quote)
            }
            type="submit"
            variant="primary"
          >
            发送
          </Button>
        </div>
      </form>
    </div>
  )
  const reportPanel = (
    <Section className="desk-report grid gap-4 p-4">
      {paper && (
        <InspectorSection label="标签、原理与知识库归属">
          <PaperTools
            paper={paper}
            books={allBooks}
            api={api}
            action={action}
            openPaper={onExternal}
            submitJob={submit}
            providerId={providerId}
            model={model}
            revision={revision}
            onTag={tag => {
              setNeighborTag(tag)
              setPane('neighbors')
            }}
            reload={async () => {
              await loadSources()
              setPaper(await api(`/papers/${paper.id}`))
            }}
          />
        </InspectorSection>
      )}
      {paper && (
        <Toolbar label="论文操作">
          <a className="fastui-link" href={`${API_BASE}/papers/${paper.id}/export`} download>
            导出 Markdown
          </a>
          <Button
            variant="danger"
            onClick={() => {
              if (window.confirm('归档这篇论文？可在归档列表恢复。'))
                void action(async () => {
                  await api(`/papers/${paper.id}`, 'DELETE')
                  onHome()
                })
            }}
          >
            归档论文
          </Button>
        </Toolbar>
      )}
      <h2 className="fastui-heading m-0 text-base">阅读报告</h2>

      <Button
        disabled={
          !paper ||
          !providerId ||
          jobs.some(
            (j: Row) =>
              j.kind === 'report' &&
              j.resource_id === paper?.id &&
              ['queued', 'running'].includes(j.state)
          )
        }
        onClick={() =>
          void action(() =>
            submit(`/papers/${paper?.id}/reports`, { provider_id: providerId, model })
          )
        }
        type="button"
        variant="primary"
      >
        {report ? '重新生成报告' : '生成阅读报告'}
      </Button>
      {report && (
        <>
          {['key_questions', 'process', 'contributions'].map(k => (
            <div key={k}>
              <h3 className="fastui-heading m-0 text-sm">
                {{ key_questions: '关键问题', process: '方法过程', contributions: '主要贡献' }[k]}
              </h3>
              {report.content[k]?.map((r: Row, i: number) => (
                <article key={i} className="fastui-section min-w-0 p-5">
                  <b>{r.question || r.step || r.title}</b>
                  <ReactMarkdown>{r.answer || r.description || ''}</ReactMarkdown>
                  {r.evidence?.map((ev: Row, j: number) => (
                    <Button
                      key={j}
                      className="citation-chip h-auto text-left whitespace-normal"
                      title={ev.exact_quote}
                      onClick={() =>
                        void action(() => locate({ ...ev, version_id: report.version_id }))
                      }
                      type="button"
                      variant="quiet"
                    >
                      第 {ev.page_start || ev.page} 页 · 查看依据
                    </Button>
                  ))}
                </article>
              ))}
            </div>
          ))}
          <a
            href={`${API_BASE}/papers/${paper?.id}/export`}
            download
            className="fastui-link break-words"
          >
            导出报告
          </a>
        </>
      )}
    </Section>
  )
  const paneId = `research-${scopeId}-${pane}`
  const paneHeader = (
    <WorkspaceTabs
      equal
      label="研究工具"
      activeId={paneId}
      tabs={(
        [
          ['chat', '对话', MessageSquare],
          ['notes', '笔记', StickyNote],
          ['report', '报告', BookOpen],
          ['neighbors', '近邻', Network],
        ] as const
      ).map(([id, label, Icon]) => ({
        icon: <Icon size={15} />,
        id: `research-${scopeId}-${id}`,
        label,
        controls: `research-panel-${scopeId}`,
      }))}
      onSelect={id => setPane(id.slice(`research-${scopeId}-`.length))}
    />
  )
  const companion =
    pane === 'chat' ? (
      chat
    ) : pane === 'report' ? (
      reportPanel
    ) : paper ? (
      <Neighbors
        key={paper.id + neighborTag}
        initialTag={neighborTag}
        paper={paper}
        api={api}
        action={action}
        openPaper={onExternal}
        submitJob={submit}
        revision={revision}
        pending={jobs.some(
          (j: Row) =>
            j.kind === 'neighbors' &&
            j.resource_id === paper.id &&
            ['queued', 'running'].includes(j.state)
        )}
      />
    ) : null
  return (
    <Section className="notebook-desk grid min-h-full min-w-0 grid-cols-1 xl:h-full xl:min-h-0 lg:grid-cols-[19rem_minmax(0,1fr)] xl:grid-rows-[minmax(0,1fr)]">
      <WorkbenchSidebar
        id="desk-sources"
        label="阅读工作区工具"
        tools={[
          {
            label: '资料',
            icon: <Files size={20} />,
            active: true,
            onClick: () =>
              document.querySelector<HTMLInputElement>('#desk-sources input[placeholder]')?.focus(),
          },
          {
            label: '添加资料',
            icon: <Plus size={20} />,
            onClick: () =>
              void action(async () => {
                setAdding(true)
                setLibrary((await api('/papers?limit=100')).items)
              }),
          },
          { label: '查看关系矩阵', icon: <Network size={20} />, onClick: () => setMatrix(true) },
          { label: '所有知识库', icon: <ArrowLeft size={20} />, onClick: onHome },
        ]}
      >
        <div className="desk-sources grid min-w-0 content-start gap-5 p-4">
          <h1 className="fastui-heading m-0 text-base">{book?.name || '论文阅读'}</h1>
          <PanelHeader className="section-heading">
            <h2 className="fastui-heading m-0 text-base">资料</h2>
            <Button
              className="quiet"
              onClick={() =>
                void action(async () => {
                  setAdding(true)
                  setLibrary((await api('/papers?limit=100')).items)
                })
              }
              type="button"
              variant="quiet"
            >
              <Plus size={16} /> 添加
            </Button>
          </PanelHeader>
          <TextField
            aria-label="筛选知识库资料"
            placeholder="筛选资料…"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="w-full"
          />
          <label className="select-sources fastui-field">
            <Checkbox
              checked={!!sources.length && checked.length === sources.length}
              onChange={e => setChecked(e.target.checked ? sources.map(p => p.id) : [])}
            />
            选择全部{' '}
            <span>
              {checked.length} / {sources.length}
            </span>
          </label>
          <nav aria-label="知识库资料" className="max-h-64 overflow-auto lg:max-h-none">
            {sources
              .filter(p => p.title.toLowerCase().includes(filter.toLowerCase()))
              .map(p => (
                <ListRow
                  className="desk-source"
                  aria-current={paper?.id === p.id ? 'true' : undefined}
                  key={p.id}
                >
                  <Checkbox
                    aria-label={`问答参考 ${p.title}`}
                    checked={checked.includes(p.id)}
                    onChange={e =>
                      setChecked(ids =>
                        e.target.checked ? [...ids, p.id] : ids.filter(id => id !== p.id)
                      )
                    }
                  />
                  <Button
                    className="h-auto text-left whitespace-normal"
                    aria-pressed={paper?.id === p.id}
                    onClick={() => void action(() => open(p.id))}
                    type="button"
                    variant="navigation"
                  >
                    <FileText className="shrink-0" size={16} />
                    <span>{p.title}</span>
                  </Button>
                </ListRow>
              ))}
          </nav>
        </div>
      </WorkbenchSidebar>
      <div className="desk-reading flex min-h-0 min-w-0 flex-col gap-5 p-4 xl:p-5">
        <div className="desk-reading-heading flex shrink-0 flex-wrap items-center justify-between gap-3">
          <div>
            <span>{book ? book.name : '论文阅读'}</span>
            <h2 className="fastui-heading m-0 text-base">{paper?.title || '添加资料，开始阅读'}</h2>
          </div>
          {paper && (
            <InspectorSection label="文档版本">
              <Select
                aria-label="文档版本"
                value={version}
                onChange={e => {
                  setVersion(e.target.value)
                  setPage(1)
                  setCitation(null)
                }}
                className="w-full"
              >
                {paper.versions.map((v: Row) => (
                  <option key={v.id} value={v.id}>
                    {new Date(v.created * 1000).toLocaleDateString()}
                    {v.id === paper.active_version ? '（当前）' : ''}
                  </option>
                ))}
              </Select>
            </InspectorSection>
          )}
        </div>
        {paper ? (
          <PdfReader
            key={paper.id}
            paper={paper}
            version={version}
            page={page}
            setPage={setPage}
            api={api}
            summary={summary}
            setSummary={setSummary}
            onSaved={s => setPaper(p => (p ? { ...p, summary: s } : p))}
            pane={pane}
            onPane={setPane}
            onQuote={capture}
            citation={citation}
            companion={companion}
            companionHeader={paneHeader}
            panelId={`research-panel-${scopeId}`}
            labelledBy={paneId}
            notebookNotes={notebookNotes}
          />
        ) : (
          <div className="desk-empty grid gap-4 p-6">
            <FileText size={40} />
            <h2 className="fastui-heading m-0 text-base">把论文放进来</h2>
            <p className="m-0 leading-relaxed break-words">
              {book?.description || '上传 PDF 或添加已有论文。'}
            </p>
            <Button
              onClick={() =>
                void action(async () => {
                  setAdding(true)
                  setLibrary((await api('/papers?limit=100')).items)
                })
              }
              type="button"
              variant="primary"
            >
              添加资料
            </Button>
          </div>
        )}
        {notice && (
          <StatusBar className="desk-toast">
            {notice}
            <Button className="quiet" onClick={() => setNotice('')} type="button" variant="quiet">
              关闭
            </Button>
          </StatusBar>
        )}
      </div>
      <AppDialog open={matrix} onClose={() => setMatrix(false)} title="关系矩阵">
        <p className="desk-muted m-0 text-sm leading-relaxed break-words">
          选择标签以限定问答范围。
        </p>
        <div
          className="matrix-scroll fastui-table-scroll"
          role="region"
          aria-label="论文与标签"
          tabIndex={0}
        >
          <table className="relation-matrix fastui-table w-full">
            <thead>
              <tr>
                <th>论文</th>
                {[...new Set<string>(sources.flatMap(p => p.tags || []))].map(t => (
                  <th key={t}>
                    <Button
                      className="tag"
                      onClick={() => {
                        setChecked(sources.filter(p => p.tags?.includes(t)).map(p => p.id))
                        setMatrix(false)
                        setPane('chat')
                      }}
                      type="button"
                      variant="quiet"
                    >
                      {t}
                    </Button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sources.map(p => (
                <tr key={p.id}>
                  <th>
                    <Button
                      className="quiet"
                      onClick={() => {
                        void action(() => open(p.id))
                        setMatrix(false)
                      }}
                      type="button"
                      variant="quiet"
                    >
                      {p.title}
                    </Button>
                  </th>
                  {[...new Set<string>(sources.flatMap(p => p.tags || []))].map(t => (
                    <td key={t}>{p.tags?.includes(t) ? '●' : '—'}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AppDialog>
      <AppDialog open={adding} onClose={() => setAdding(false)} title="添加资料">
        <form
          onSubmit={e => {
            e.preventDefault()
            void action(async () => {
              await submit('/imports/url', { url, knowledge_id: target.book_id || '' })
              setUrl('')
              setAdding(false)
            })
          }}
          className="grid min-w-0 gap-3"
        >
          <label className="fastui-field">
            论文链接
            <TextField
              value={url}
              onChange={e => setUrl(e.target.value)}
              type="url"
              required
              placeholder="https://arxiv.org/pdf/…"
              className="w-full"
            />
          </label>
          <Button type="submit" variant="primary">
            导入链接
          </Button>
        </form>
        <label className="file-button fastui-field">
          上传 PDF
          <TextField
            aria-label="上传资料 PDF"
            type="file"
            accept="application/pdf"
            onChange={e => {
              const file = e.target.files?.[0]
              if (file)
                void action(async () => {
                  const data = new FormData()
                  data.set('file', file)
                  data.set('knowledge_id', target.book_id || '')
                  await submit('/imports/pdf', data)
                  setAdding(false)
                })
            }}
            className="w-full"
          />
        </label>
        {scope === 'book' && (
          <>
            <h3 className="fastui-heading m-0 text-sm">从资料库添加</h3>
            {library
              .filter(p => !sources.some(s => s.id === p.id))
              .map(p => (
                <Button
                  className="add-existing quiet"
                  key={p.id}
                  onClick={() =>
                    void action(async () => {
                      await api(`/knowledge-bases/${scopeId}/papers`, 'POST', { paper_ids: [p.id] })
                      await loadSources()
                      setChecked(ids => [...new Set([...ids, p.id])])
                      if (!paper) await open(p.id)
                      setAdding(false)
                    })
                  }
                  type="button"
                  variant="quiet"
                >
                  <Plus size={15} />
                  {p.title}
                </Button>
              ))}
          </>
        )}
      </AppDialog>
    </Section>
  )
}
