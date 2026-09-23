import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Archive,
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  Check,
  Clock3,
  FileText,
  LibraryBig,
  LoaderCircle,
  Moon,
  PanelLeft,
  Plus,
  Search,
  Settings2,
  StickyNote,
  Sun,
  X,
} from 'lucide-react'
import 'katex/dist/katex.min.css'
import './web.css'
import './reading.css'
import NotebookDesk from './NotebookDesk'
import { OrganizeProvider, type Job } from './Organize'
import Library from './Library'
import Modal from './Modal'
import Notes from './Notes'
import ImportDialog from './ImportDialog'
import { api, setCsrf, type Row } from './api'
import { useWorkspaceRoute, type WorkspaceRoute } from './navigation'
import { useTheme } from './useTheme'
import './product.css'
import './theme.css'

const jobNames: Record<string, string> = {
  import_pdf: '导入 PDF',
  import_url: '导入链接',
  organize: '整理论文',
  report: '生成报告',
  chat: '论文问答',
  knowledge_chat: '知识库问答',
  neighbors: '查找相关论文',
}
const jobStates: Record<string, string> = {
  queued: '排队中',
  running: '处理中',
  succeeded: '已完成',
  failed: '未完成',
  needs_attention: '需要处理',
  cancelled: '已取消',
}

export default function WebApp() {
  const { theme, selectTheme } = useTheme()
  const [route, navigate] = useWorkspaceRoute()
  const [arrival] = useState(() => new URLSearchParams(window.location.search))
  const [user, setUser] = useState<Row | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [books, setBooks] = useState<Row[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [jobsOffline, setJobsOffline] = useState(false)
  const [providers, setProviders] = useState<Row[]>([])
  const [providerId, setProviderId] = useState('')
  const [model, setModel] = useState('')
  const [settings, setSettings] = useState(false)
  const [activity, setActivity] = useState(false)
  const [creating, setCreating] = useState(false)
  const [importTarget, setImportTarget] = useState<Row | null>(() =>
    arrival.has('url') || arrival.has('pending') || arrival.get('source') === 'fastnews'
      ? { paperId: arrival.get('pending') || '', url: arrival.get('url') || '' }
      : null
  )
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth >= 1100)
  const [refresh, setRefresh] = useState(0)
  const [recent, setRecent] = useState<Row | null>(null)
  const [search, setSearch] = useState(route.q || '')
  const [results, setResults] = useState<Row | null>(null)
  const [searching, setSearching] = useState(false)
  const searchGeneration = useRef(0)
  const revision = `${refresh}:${jobs.map(j => `${j.id}:${j.state}`).join(',')}`
  const inReader = !!(route.book || route.paper)
  const pendingCount = jobs.filter(j => ['queued', 'running'].includes(j.state)).length
  const done = jobs
    .filter(j => j.state === 'succeeded')
    .map(j => j.id)
    .join(',')
  const action = useCallback(async (fn: () => Promise<unknown>) => {
    setError('')
    try {
      return await fn()
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])
  useEffect(() => {
    api('/auth/me')
      .then(value => {
        setCsrf(value.csrf)
        setUser(value)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => {
    if (!user) return
    let active = true
    api('/knowledge-bases')
      .then(data => {
        if (active) setBooks(data.items)
      })
      .catch(e => {
        if (active) setError(e.message)
      })
    return () => {
      active = false
    }
  }, [user, done, refresh])
  const loadProviders = useCallback(async () => {
    const data = await api('/providers')
    setProviders(data.items)
    setProviderId(current => current || data.items[0]?.id || '')
    setModel(current => current || data.items[0]?.models[0] || '')
  }, [])
  useEffect(() => {
    if (user) void action(loadProviders)
  }, [user, action, loadProviders])
  useEffect(() => {
    if (!user) return
    let active = true
    const poll = async () => {
      try {
        const data = await api('/jobs')
        if (active) {
          setJobs(data.items)
          setJobsOffline(false)
        }
      } catch {
        if (active) setJobsOffline(true)
      }
    }
    void poll()
    const timer = window.setInterval(poll, 3000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [user])
  useEffect(() => {
    if (notice) {
      const timer = window.setTimeout(() => setNotice(''), 5000)
      return () => window.clearTimeout(timer)
    }
  }, [notice])
  useEffect(() => {
    setSearch(route.q || '')
    setError('')
  }, [route.view, route.q, route.paper, route.book])
  useEffect(() => {
    if (!user) return
    if (route.paper) localStorage.setItem(`fastread:last-paper:${user.workspace_id}`, route.paper)
    const id = route.paper || localStorage.getItem(`fastread:last-paper:${user.workspace_id}`)
    let active = true
    if (id)
      api(`/papers/${id}`)
        .then(p => {
          if (active) setRecent(p.archived ? null : p)
        })
        .catch(() => {
          if (active) setRecent(null)
        })
    return () => {
      active = false
    }
  }, [user, route.paper, refresh])
  useEffect(() => {
    if (!user || !arrival.get('job')) return
    void action(async () => {
      const job = await api(`/jobs/${encodeURIComponent(arrival.get('job')!)}`)
      if (job.result?.paper_id) navigate({ view: 'library', paper: job.result.paper_id }, true)
      else setActivity(true)
    })
    // An incoming job link is consumed once after authentication.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user])
  function go(next: WorkspaceRoute) {
    if (window.innerWidth < 1100) setSidebarOpen(false)
    navigate(next)
  }
  async function submitJob(path: string, body?: unknown) {
    const job = await api(path, 'POST', body, crypto.randomUUID())
    setJobs(current => [job, ...current.filter(j => j.id !== job.id)])
    return job
  }
  useEffect(() => {
    const generation = ++searchGeneration.current
    if (!user || route.view !== 'discover' || !route.q) {
      setResults(null)
      setSearching(false)
      return
    }
    setSearching(true)
    setResults(null)
    api('/search', 'POST', { query: route.q })
      .then(data => {
        if (searchGeneration.current === generation) setResults(data)
      })
      .catch(e => {
        if (searchGeneration.current === generation) setError(e.message)
      })
      .finally(() => {
        if (searchGeneration.current === generation) setSearching(false)
      })
  }, [user, route.view, route.q, refresh])
  if (loading)
    return (
      <div className="product-start">
        <BookOpen size={28} />
        <p>正在打开文献库…</p>
      </div>
    )
  if (!user)
    return (
      <main className="product-start">
        <BookOpen size={28} />
        <h1>暂时无法打开文献库</h1>
        <p>{error || '请从 FastResearch 重新进入。'}</p>
        <button onClick={() => window.location.reload()}>重新连接</button>
      </main>
    )

  return (
    <OrganizeProvider jobs={jobs} submit={submitJob} api={api}>
      <div
        className={`product-app ${inReader ? 'reader-mode' : ''} ${sidebarOpen ? 'navigation-open' : ''}`}
      >
        <a className="skip-link" href="#main-content">
          跳到主要内容
        </a>
        {!inReader && (
          <>
            {sidebarOpen && (
              <button
                className="navigation-scrim"
                aria-label="关闭导航"
                onClick={() => setSidebarOpen(false)}
              />
            )}
            <aside className="product-navigation" aria-label="主导航" inert={!sidebarOpen}>
              <button className="product-brand quiet" onClick={() => go({ view: 'library' })}>
                <span>
                  <BookOpen size={20} />
                </span>
                FastRead
                <span className="brand-dot" />
              </button>
              <div className="workspace-label">
                <span className="workspace-avatar">{(user.workspace.name || 'F').slice(0, 1)}</span>
                <span>{user.workspace.name}</span>
              </div>
              <nav>
                {(
                  [
                    ['library', '文献库', FileText],
                    ['books', '知识库', LibraryBig],
                    ['notes', '笔记', StickyNote],
                  ] as const
                ).map(([view, label, Icon]) => (
                  <button
                    key={view}
                    className={`nav-item ${route.view === view ? 'active' : ''}`}
                    aria-current={route.view === view ? 'page' : undefined}
                    onClick={() => go({ view })}
                  >
                    <Icon size={18} />
                    {label}
                    {view === 'books' && <small>{books.length}</small>}
                  </button>
                ))}
              </nav>
              <div className="nav-section-title">
                <span>我的知识库</span>
                <button
                  className="icon-button quiet"
                  aria-label="新建知识库"
                  onClick={() => setCreating(true)}
                >
                  <Plus size={14} />
                </button>
              </div>
              <nav className="collection-nav">
                {books.slice(0, 8).map(b => (
                  <button
                    className="nav-item"
                    key={b.id}
                    onClick={() => go({ view: 'books', book: b.id })}
                  >
                    <span className="collection-dot" />
                    <span>{b.name}</span>
                    <small>{b.paper_count}</small>
                  </button>
                ))}
                {!books.length && <p>按研究问题收集论文</p>}
                {books.length > 8 && (
                  <button className="nav-item" onClick={() => go({ view: 'books' })}>
                    查看全部知识库
                  </button>
                )}
              </nav>
              <div className="nav-bottom">
                <button
                  className={`nav-item ${route.view === 'archive' ? 'active' : ''}`}
                  onClick={() => go({ view: 'archive' })}
                >
                  <Archive size={17} />
                  已归档
                </button>
                <button className="nav-item" onClick={() => setSettings(true)}>
                  <Settings2 size={17} />
                  设置
                </button>
                <div className="account-label">
                  <span className="account-avatar">
                    {(user.display_name || user.email || '我').slice(0, 1).toUpperCase()}
                  </span>
                  <span>
                    {user.display_name || (user.public ? '共享资料库' : user.email)}
                    <small>研究工作区</small>
                  </span>
                </div>
              </div>
            </aside>
          </>
        )}
        <div className="product-body">
          <header className="product-topbar">
            <div>
              <button
                className="icon-button quiet"
                aria-label={sidebarOpen ? '收起侧栏' : '展开侧栏'}
                aria-expanded={sidebarOpen}
                onClick={() => setSidebarOpen(open => !open)}
              >
                <PanelLeft size={18} />
              </button>
              {inReader ? (
                <button
                  className="breadcrumb quiet"
                  onClick={() => go({ view: route.book ? 'books' : 'library' })}
                >
                  <ArrowLeft size={14} />
                  {route.book ? '知识库' : '文献库'}
                </button>
              ) : (
                <span className="breadcrumb">
                  工作区<span>/</span>
                  {
                    {
                      library: '文献库',
                      books: '知识库',
                      notes: '笔记',
                      archive: '已归档',
                      discover: '发现论文',
                    }[route.view]
                  }
                </span>
              )}
            </div>
            <div className="topbar-actions">
              <button
                className="icon-button quiet theme-toggle"
                aria-label={theme === 'dark' ? '切换到白天模式' : '切换到夜间模式'}
                title={theme === 'dark' ? '切换到白天模式' : '切换到夜间模式'}
                onClick={() => selectTheme(theme === 'dark' ? 'light' : 'dark')}
              >
                {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
              </button>
              <button className="quiet discover-button" onClick={() => go({ view: 'discover' })}>
                <Search size={15} />
                搜索公开论文
              </button>
              <button
                className={`quiet activity-button ${pendingCount ? 'has-pending' : ''}`}
                onClick={() => setActivity(true)}
              >
                {pendingCount ? (
                  <LoaderCircle className="spinning" size={15} />
                ) : (
                  <Clock3 size={15} />
                )}
                处理记录
                {jobsOffline ? (
                  <span>连接中断</span>
                ) : (
                  pendingCount > 0 && <span>{pendingCount}</span>
                )}
              </button>
              {inReader && (
                <button
                  className="icon-button quiet"
                  aria-label="设置"
                  onClick={() => setSettings(true)}
                >
                  <Settings2 size={17} />
                </button>
              )}
            </div>
          </header>
          {error && (
            <div className="product-error" role="alert">
              <span>{error}</span>
              <button className="quiet" onClick={() => setError('')} aria-label="关闭错误提示">
                <X size={16} />
              </button>
            </div>
          )}
          <main id="main-content" className="product-main" tabIndex={-1}>
            {inReader ? (
              <NotebookDesk
                key={route.book || route.paper}
                target={{
                  book_id: route.book,
                  paper_id: route.paper,
                  page: route.page,
                  version: route.version,
                }}
                api={api}
                action={action}
                jobs={jobs}
                providerId={providerId}
                model={model}
                sidebarOpen={sidebarOpen}
                onHome={() => go({ view: route.book ? 'books' : 'library' })}
                onExternal={(id: string) => go({ view: 'library', paper: id })}
                onLocation={(id: string, page: number, version: string) =>
                  navigate({ ...route, paper: id, page, version }, true)
                }
              />
            ) : route.view === 'notes' ? (
              <Notes books={books} navigate={go} revision={revision} />
            ) : route.view === 'discover' ? (
              <section className="library-page discover-page">
                <div className="page-heading">
                  <div>
                    <div className="page-kicker">公开学术来源</div>
                    <h1>发现论文</h1>
                    <p>按标题、DOI 或关键词搜索，确认来源后收入文献库。</p>
                  </div>
                </div>
                <form
                  className="discovery-search"
                  onSubmit={e => {
                    e.preventDefault()
                    go({ view: 'discover', q: search.trim() })
                  }}
                >
                  <Search size={20} />
                  <input
                    aria-label="搜索公开论文"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    placeholder="论文标题、DOI 或研究关键词"
                    required
                    maxLength={300}
                  />
                  <button disabled={searching}>{searching ? '搜索中…' : '搜索'}</button>
                </form>
                {!route.q && (
                  <div className="product-empty">
                    <Search size={30} />
                    <h2>从一个研究问题开始查找</h2>
                    <p>搜索公开来源不会改变已有文献。</p>
                  </div>
                )}
                {searching && (
                  <p role="status" className="search-progress">
                    正在查找公开来源…
                  </p>
                )}
                {results && (
                  <>
                    <details className="source-status">
                      <summary>检索来源状态</summary>
                      {Object.entries(results.sources || {}).map(([name, status]) => (
                        <p key={name}>
                          {name} ·{' '}
                          {(status as Row).available
                            ? '可用'
                            : (status as Row).reason || '暂不可用'}
                        </p>
                      ))}
                    </details>
                    {!results.papers.length && (
                      <div className="product-empty">
                        <h2>未找到匹配的论文</h2>
                        <p>试试更完整的标题或 DOI，也可以直接导入 PDF。</p>
                      </div>
                    )}
                    <div className="discovery-results">
                      {results.papers.map((p: Row, i: number) => (
                        <article key={p.id || i}>
                          <div className="result-index">{String(i + 1).padStart(2, '0')}</div>
                          <div>
                            <h2>{p.title}</h2>
                            <p className="result-meta">
                              {p.authors?.join(', ')} · {p.year || '年份待核实'}
                            </p>
                            <p className="result-abstract">{p.abstract}</p>
                            {p.identity_warning && (
                              <p className="inline-warning">{p.identity_warning}</p>
                            )}
                            <div className="toolbar">
                              <small>
                                {p.discovery_sources?.join(' · ')}
                                {p.doi && ` · ${p.doi}`}
                              </small>
                              <a
                                href={p.pdf_url || p.url || p.source_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                查看来源 <ArrowUpRight size={13} />
                              </a>
                              <button
                                className="quiet"
                                onClick={() =>
                                  setImportTarget({
                                    url:
                                      p.pdf_url ||
                                      p.url ||
                                      p.source_url ||
                                      `https://doi.org/${p.doi}`,
                                  })
                                }
                              >
                                <Plus size={14} />
                                导入
                              </button>
                            </div>
                          </div>
                        </article>
                      ))}
                    </div>
                  </>
                )}
              </section>
            ) : (
              <Library
                route={route}
                navigate={go}
                books={books}
                revision={revision}
                providerId={providerId}
                model={model}
                onImport={paperId => setImportTarget({ paperId })}
                onCreateBook={() => setCreating(true)}
                onChanged={() => setRefresh(n => n + 1)}
                notify={setNotice}
                recent={recent}
              />
            )}
          </main>
        </div>
        {notice && (
          <div className="product-toast" role="status">
            <Check size={16} />
            <span>{notice}</span>
            <button className="quiet" aria-label="关闭通知" onClick={() => setNotice('')}>
              <X size={14} />
            </button>
          </div>
        )}
        {importTarget && (
          <ImportDialog
            target={importTarget}
            books={books}
            providers={providers}
            submit={submitJob}
            onClose={() => setImportTarget(null)}
            onComplete={() => {
              setImportTarget(null)
              setNotice('已开始导入，进度可在「处理记录」查看。关闭页面后仍会继续。')
            }}
          />
        )}
        {creating && (
          <Modal
            title="新建知识库"
            description="用一个主题或研究问题，把相关论文放在一起。"
            onClose={() => setCreating(false)}
          >
            <form
              onSubmit={e => {
                e.preventDefault()
                const form = e.currentTarget
                void action(async () => {
                  const book = await api(
                    '/knowledge-bases',
                    'POST',
                    Object.fromEntries(new FormData(form))
                  )
                  setCreating(false)
                  setRefresh(n => n + 1)
                  go({ view: 'books', book: book.id })
                })
              }}
            >
              <label>
                名称
                <input name="name" placeholder="例如：检索增强生成" maxLength={80} required />
              </label>
              <label>
                关注的问题 <small>选填</small>
                <textarea
                  name="description"
                  placeholder="希望通过这些论文弄清什么？"
                  maxLength={1000}
                  rows={3}
                />
              </label>
              {error && (
                <p className="inline-error" role="alert">
                  {error}
                </p>
              )}
              <div className="dialog-footer">
                <button type="button" className="quiet" onClick={() => setCreating(false)}>
                  取消
                </button>
                <button>创建知识库</button>
              </div>
            </form>
          </Modal>
        )}
        {activity && (
          <Modal
            title="处理记录"
            description="导入和生成任务在服务器继续执行，可以离开这个页面。"
            onClose={() => setActivity(false)}
          >
            <div className="activity-list">
              {jobsOffline && (
                <p className="inline-error" role="status">
                  暂时无法更新任务状态，显示的是上次读取的记录。连接恢复后会自动更新。
                </p>
              )}
              {!jobs.length && !jobsOffline && (
                <div className="product-empty">
                  <Clock3 size={26} />
                  <p>暂时没有处理记录</p>
                </div>
              )}
              {jobs.map(j => (
                <div className="activity-row" key={j.id}>
                  <span className={`job-icon ${j.state}`}>
                    {['queued', 'running'].includes(j.state) ? (
                      <LoaderCircle size={17} className="spinning" />
                    ) : j.state === 'succeeded' ? (
                      <Check size={17} />
                    ) : (
                      <Clock3 size={17} />
                    )}
                  </span>
                  <div>
                    <strong>{jobNames[j.kind] || '后台处理'}</strong>
                    <p>
                      {jobStates[j.state] || j.state}
                      {j.created &&
                        ` · ${new Date(j.created * 1000).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`}
                    </p>
                    {j.error && <p className="job-error">{j.error}</p>}
                  </div>
                  {j.result?.paper_id && (
                    <button
                      className="quiet"
                      onClick={() => {
                        setActivity(false)
                        go({ view: 'library', paper: j.result.paper_id })
                      }}
                    >
                      打开
                      <ArrowUpRight size={14} />
                    </button>
                  )}
                </div>
              ))}
            </div>
            <div className="dialog-footer">
              <button
                className="quiet"
                onClick={() =>
                  void action(async () => {
                    setJobs((await api('/jobs')).items)
                    setJobsOffline(false)
                  })
                }
              >
                刷新记录
              </button>
            </div>
            {error && (
              <p className="inline-error" role="alert">
                {error}
              </p>
            )}
          </Modal>
        )}
        {settings && (
          <Modal
            title="工作区设置"
            description="模型用于论文报告、问答和整理。阅读已有原文不需要模型。"
            onClose={() => setSettings(false)}
          >
            <fieldset className="theme-settings">
              <legend>外观</legend>
              <div className="segmented-control" role="group" aria-label="外观模式">
                <button
                  type="button"
                  className={theme === 'light' ? 'active' : ''}
                  aria-pressed={theme === 'light'}
                  onClick={() => selectTheme('light')}
                >
                  <Sun size={16} />
                  白天
                </button>
                <button
                  type="button"
                  className={theme === 'dark' ? 'active' : ''}
                  aria-pressed={theme === 'dark'}
                  onClick={() => selectTheme('dark')}
                >
                  <Moon size={16} />
                  夜间
                </button>
              </div>
            </fieldset>
            <label>
              当前模型
              <select
                value={`${providerId}|${model}`}
                onChange={e => {
                  const [p, m] = e.target.value.split('|')
                  setProviderId(p)
                  setModel(m)
                }}
              >
                <option value="|" disabled>
                  尚未配置模型
                </option>
                {providers.flatMap(p =>
                  p.models.map((m: string) => (
                    <option key={`${p.id}|${m}`} value={`${p.id}|${m}`}>
                      {m} · {p.name}
                    </option>
                  ))
                )}
              </select>
            </label>
            <p className="settings-note">
              24 小时模型任务上限：{user.workspace.daily_limit}。供应商配置由工作区管理员管理。
            </p>
            {user.role === 'owner' && (
              <details className="provider-settings">
                <summary>添加模型供应商</summary>
                <form
                  onSubmit={e => {
                    e.preventDefault()
                    const form = e.currentTarget
                    const data = Object.fromEntries(new FormData(form))
                    void action(async () => {
                      await api('/providers', 'POST', {
                        ...data,
                        models: String(data.models)
                          .split(',')
                          .map(m => m.trim())
                          .filter(Boolean),
                      })
                      form.reset()
                      await loadProviders()
                      setNotice('供应商已保存')
                    })
                  }}
                >
                  <label>
                    名称
                    <input name="name" required />
                  </label>
                  <label>
                    API 地址
                    <input
                      type="url"
                      name="base_url"
                      placeholder="https://api.example.com/v1"
                      required
                    />
                  </label>
                  <label>
                    API 密钥
                    <input type="password" name="api_key" autoComplete="off" required />
                  </label>
                  <label>
                    模型 ID
                    <input name="models" placeholder="多个模型用逗号分隔" required />
                  </label>
                  <button>保存供应商</button>
                </form>
              </details>
            )}
            {error && (
              <p className="inline-error" role="alert">
                {error}
              </p>
            )}
            {!user.public && (
              <div className="dialog-footer">
                <button
                  className="quiet"
                  onClick={() =>
                    void action(async () => {
                      await api('/auth/logout', 'POST')
                      window.location.reload()
                    })
                  }
                >
                  退出登录
                </button>
              </div>
            )}
          </Modal>
        )}
      </div>
    </OrganizeProvider>
  )
}
