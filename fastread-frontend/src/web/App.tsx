import { arrivalParameters, clearCASDestination } from './authReturn'
import { APP_BASE, API_BASE } from './urls'
import { useCallback, useEffect, useState } from 'react'
import {
  ActivityRail,
  Alert,
  Button,
  Loading,
  PanelHeader,
  Section,
  Select,
  StatusBar,
  TextField,
  Toolbar,
} from '@fastrd/ui-react'
import LocalLogin from './LocalLogin'
import FastCASAccount from './FastCASAccount'
import Knowledge from './Knowledge'
import { OrganizeProvider, type Job } from './Organize'
import NotebookDesk from './NotebookDesk'
import PaperSearch from './PaperSearch'
import Jobs from './Jobs'
import {
  AppDialog,
  AppHeader,
  WorkbenchSidebar,
  SideTabWorkspace,
  type MainSection,
} from './Chrome'
import {
  Archive,
  Files,
  Palette,
  SlidersHorizontal,
  Link2,
  ListTodo,
  FileText,
  FolderOpen,
  ChevronRight,
} from 'lucide-react'
import { Administration } from './Admin'
import { IntegrationStatus } from './Integrations'
import { submitFastNews, type FastNewsHandoff } from './sso-bootstrap'
import { colorMode } from './theme'
import './workbench.css'

type Row = Record<string, any>
let csrf = ''
const pendingReads = new Map<string, Promise<any>>()
function api(path: string, method = 'GET', body?: unknown, key?: string): Promise<any> {
  if (method !== 'GET') {
    pendingReads.clear()
    return request(path, method, body, key).finally(() => pendingReads.clear())
  }
  const pending = pendingReads.get(path)
  if (pending) return pending
  const promise = request(path, method, body, key).finally(() => {
    if (pendingReads.get(path) === promise) pendingReads.delete(path)
  })
  pendingReads.set(path, promise)
  return promise
}
async function request(path: string, method = 'GET', body?: unknown, key?: string) {
  const headers: Record<string, string> = {}
  if (csrf) headers['X-CSRF-Token'] = csrf
  if (key) headers['Idempotency-Key'] = key
  if (body && !(body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    credentials: 'same-origin',
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  })
  const value = await response.json()
  if (!response.ok)
    throw new Error(typeof value.detail === 'string' ? value.detail : '请求未通过校验')
  return value
}

function FastNewsNotice({
  handoff,
  onRetry,
}: {
  handoff: FastNewsHandoff | null
  onRetry?: () => void
}) {
  if (!handoff) return null
  if (handoff.status === 'invalid') return <Alert tone="danger">{handoff.error}</Alert>
  if (handoff.status === 'received')
    return (
      <Alert tone="success">
        来自 FastNews，已收入「{handoff.receipt.title}」。
        {handoff.receipt.awaiting_file ? '请自行上传 PDF。' : '原有文档已保留。'}
      </Alert>
    )
  if (handoff.status === 'login-required')
    return (
      <Alert tone="warning">
        FastNews 登录票据未完成验证，「{handoff.body.title}」尚未收入。请重新登录后继续。
      </Alert>
    )
  return (
    <Alert tone={handoff.status === 'failed' ? 'danger' : 'info'}>
      <p>
        来自 FastNews，「{handoff.body.title}」尚未收入。
        {handoff.status === 'failed'
          ? handoff.error
          : onRetry
            ? '正在收入论文信息…'
            : '请登录后继续。'}
      </p>
      {onRetry && (
        <Button onClick={onRetry} loading={handoff.status === 'pending'}>
          重试收入
        </Button>
      )}
    </Alert>
  )
}

export default function WebApp({
  initialUser,
  initialHandoff = null,
}: {
  initialUser?: Row | null
  initialHandoff?: FastNewsHandoff | null
}) {
  const [handoff, setHandoff] = useState(initialHandoff)
  const handoffBody = handoff && 'body' in handoff ? handoff.body : null
  const [arrival] = useState(arrivalParameters)
  const [deskTarget, setDeskTarget] = useState<Row | null>(
    arrival.get('book') ? { book_id: arrival.get('book') } : null
  )
  const [user, setUser] = useState<Row | null>(() => {
    if (initialUser) csrf = initialUser.csrf
    return initialUser || null
  })
  const [loading, setLoading] = useState(initialUser === undefined)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(
    arrival.get('fastcas') === 'complete'
      ? 'FastCAS 操作已完成'
      : arrival.get('fastcas') === 'failed'
        ? 'FastCAS 操作未完成；可在账号设置检查状态或重试。'
        : ''
  )
  const [papers, setPapers] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [archived, setArchived] = useState(false)
  const [jobs, setJobs] = useState<Job[]>([])
  const [providers, setProviders] = useState<Row[]>([])
  const [providerId, setProviderId] = useState('')
  const [model, setModel] = useState('')
  const [metadataModel, setMetadataModel] = useState('')
  const [searchReturn, setSearchReturn] = useState<Row | null>(null)
  const [section, setSection] = useState<MainSection>(
    arrival.get('section') === 'settings' ? 'settings' : 'library'
  )
  const [libraryPage, setLibraryPage] = useState<'papers' | 'jobs' | 'search'>('papers')
  const [libraryEpoch, setLibraryEpoch] = useState(0)
  const [themeMode, setThemeMode] = useState(colorMode.mode)
  const [accountSettings, setAccountSettings] = useState(false)
  const [books, setBooks] = useState<Row[]>([])
  const [libraryDialog, setLibraryDialog] = useState<'import' | null>(null)
  const [importBook, setImportBook] = useState('')
  const [importUrl, setImportUrl] = useState(handoffBody?.url || arrival.get('url') || '')
  useEffect(() => colorMode.subscribe(() => setThemeMode(colorMode.mode)), [])
  useEffect(() => {
    if (handoff || arrival.has('url') || arrival.has('pending')) setLibraryDialog('import')
  }, [arrival, handoff])

  const action = useCallback(async (fn: () => Promise<unknown>) => {
    setError('')
    setNotice('')
    try {
      return await fn()
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])
  const loadLibrary = useCallback(async () => {
    const [data, libraries] = await Promise.all([
      api(`/papers?limit=20&offset=${offset}&archived=${archived}`),
      api('/knowledge-bases'),
    ])
    setPapers(data.items)
    setTotal(data.total)
    setBooks(libraries.items)
  }, [offset, archived])
  async function retryFastNews() {
    if (!handoffBody || handoff?.status === 'pending') return
    const body = handoffBody
    setHandoff({ status: 'pending', body })
    try {
      setHandoff({ status: 'received', body, receipt: await submitFastNews(body, csrf) })
      await loadLibrary()
    } catch (error) {
      setHandoff({ status: 'failed', body, error: (error as Error).message })
    }
  }
  const loadProviders = useCallback(async (selection?: { providerId: string; model: string }) => {
    const data = await api('/providers')
    setProviders(data.items)
    if (
      !selection ||
      !data.items.some(
        (p: Row) => p.id === selection.providerId && p.models.includes(selection.model)
      )
    ) {
      setProviderId(data.items[0]?.id || '')
      setModel(data.items[0]?.models[0] || '')
      const qwen = data.items
        .flatMap((p: Row) => p.models.map((m: string) => ({ provider: p.id, model: m })))
        .find((v: Row) => /qwen/i.test(v.model) && /27b/i.test(v.model))
      setMetadataModel(qwen ? `${qwen.provider}|${qwen.model}` : '')
    }
  }, [])
  const openPaper = useCallback(async (id: string, page?: number, version?: string) => {
    setDeskTarget({ paper_id: id, page, version })
    window.history.replaceState(null, '', APP_BASE + '?paper=' + encodeURIComponent(id))
  }, [])
  function home() {
    setLibraryPage('papers')
    setArchived(false)
    setOffset(0)
    setLibraryEpoch(n => n + 1)
    setDeskTarget(null)
    window.history.replaceState(null, '', APP_BASE)
    void action(loadLibrary)
  }
  useEffect(() => {
    if (initialUser === undefined)
      api('/auth/me')
        .then(data => {
          csrf = data.csrf
          setUser(data)
        })
        .catch(() => {})
        .finally(() => setLoading(false))
  }, [initialUser])
  useEffect(() => {
    if (user) {
      clearCASDestination()
      void action(loadLibrary)
    }
  }, [user, action, loadLibrary])
  useEffect(() => {
    if (user) void action(loadProviders)
  }, [user, action, loadProviders])
  useEffect(() => {
    if (!user) return
    if (arrival.get('paper')) void openPaper(arrival.get('paper')!)
    if (arrival.get('job'))
      void action(async () => {
        const job = await api('/jobs/' + encodeURIComponent(arrival.get('job')!))
        if (job.result?.paper_id) await openPaper(job.result.paper_id)
      })
  }, [user, arrival, action, openPaper])
  useEffect(() => {
    if (!user) return
    let stopped = false,
      previous: string | undefined
    async function refresh() {
      try {
        const data = await api('/jobs')
        if (stopped) return
        setJobs(data.items)
        const completed = data.items
          .filter((j: Row) => j.state === 'succeeded')
          .map((j: Row) => j.id)
          .join(',')
        if (previous !== undefined && completed !== previous) await loadLibrary()
        previous = completed
      } catch (e) {
        if (!stopped) setError((e as Error).message)
      }
    }
    void refresh()
    const timer = setInterval(refresh, 3000)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [user, loadLibrary])
  async function submitJob(path: string, body?: unknown) {
    if (path.startsWith('/imports/')) {
      if (body instanceof FormData) body.set('knowledge_id', importBook)
      else body = { ...(body as Row), knowledge_id: importBook }
      if (metadataModel) {
        const [provider_id, model] = metadataModel.split('|')
        if (body instanceof FormData) {
          body.set('provider_id', provider_id)
          body.set('model', model)
        } else body = { ...(body as Row), provider_id, model }
      }
    }
    const job = await api(path, 'POST', body, crypto.randomUUID())
    setJobs(current => [job, ...current.filter(j => j.id !== job.id)])
    setNotice(path.endsWith('/organize') ? '' : '任务已交给服务器，关闭网页后仍会继续。')
    return job
  }
  const modelOptions = providers.flatMap(p =>
    p.models.map((m: string) => (
      <option key={`${p.id}|${m}`} value={`${p.id}|${m}`}>
        {m} · {p.name}
        {p.shared ? '（公用）' : ''}
      </option>
    ))
  )
  if (loading)
    return (
      <main className="grid min-h-dvh place-items-center">
        <Loading label="正在连接资料库…" />
      </main>
    )
  if (!user || arrival.get('fastcas') === 'register')
    return (
      <main className="box-border grid min-h-dvh content-center justify-items-center gap-4 p-4">
        <FastNewsNotice handoff={handoff} />
        <LocalLogin />
      </main>
    )

  return (
    <OrganizeProvider jobs={jobs} submit={submitJob} api={api}>
      <div className="web-shell flex h-dvh min-w-0 flex-col overflow-hidden">
        <AppHeader
          user={user}
          section={section}
          onSection={value => {
            setSection(value)
            if (value === 'library') home()
            if (value === 'settings') void action(() => loadProviders({ providerId, model }))
          }}
          onAccount={() => setAccountSettings(true)}
          onLogout={() =>
            void action(async () => {
              await api('/auth/logout', 'POST')
              csrf = ''
              setUser(null)
              setDeskTarget(null)
              setPapers([])
              setJobs([])
            })
          }
        />
        {error && (
          <Alert tone="danger" className="shrink-0">
            <Toolbar label="错误信息">
              <span>{error}</span>
              <Button variant="quiet" onClick={() => setError('')}>
                关闭
              </Button>
            </Toolbar>
          </Alert>
        )}
        {notice && (
          <Alert tone="success" className="shrink-0">
            {notice}
          </Alert>
        )}
        <FastNewsNotice handoff={handoff} onRetry={() => void retryFastNews()} />
        <AppDialog
          open={accountSettings}
          onClose={() => setAccountSettings(false)}
          title="CAS 认证"
        >
          {accountSettings && <FastCASAccount api={api} />}
        </AppDialog>

        <AppDialog
          open={libraryDialog === 'import'}
          onClose={() => setLibraryDialog(null)}
          title="导入论文"
        >
          <div className="import-fields">
            {' '}
            <label className="fastui-field">
              标题与作者识别
              <Select
                aria-label="元数据模型"
                value={metadataModel}
                onChange={e => setMetadataModel(e.target.value)}
              >
                <option value="">版面识别与公开索引核验</option>
                {modelOptions}
              </Select>
            </label>
            {metadataModel && <small>发送首页文本，计入模型任务额度。</small>}
            <label className="fastui-field">
              目标知识库
              <Select
                aria-label="导入知识库"
                value={importBook}
                onChange={e => setImportBook(e.target.value)}
              >
                <option value="">自动归类</option>
                {books.map(b => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </Select>
            </label>
            <form
              className="grid gap-3"
              onSubmit={e => {
                e.preventDefault()
                void action(() =>
                  submitJob('/imports/url', {
                    url: importUrl,
                    source: handoffBody ? 'fastnews' : arrival.get('source') || '',
                    external_id: handoffBody?.external_id || arrival.get('external_id') || '',
                  })
                )
              }}
            >
              <label className="fastui-field">
                论文链接
                <TextField
                  name="url"
                  value={importUrl}
                  onChange={e => setImportUrl(e.target.value)}
                  type="url"
                  placeholder="https://arxiv.org/pdf/…"
                  required
                />
              </label>
              <Button type="submit">导入链接</Button>
            </form>
            <label className="fastui-field">
              上传 PDF
              <TextField
                aria-label="上传 PDF"
                type="file"
                accept="application/pdf"
                onChange={e => {
                  const file = e.target.files?.[0]
                  if (!file) return
                  const data = new FormData()
                  data.set('file', file)
                  const paperId =
                    handoff?.status === 'received' ? handoff.receipt.id : arrival.get('pending')
                  if (paperId) data.set('paper_id', paperId)
                  void action(() => submitJob('/imports/pdf', data))
                  e.target.value = ''
                }}
              />
            </label>
          </div>
        </AppDialog>
        {section !== 'library' ? (
          <main
            className="min-h-0 flex-1 overflow-auto"
            role={section === 'settings' ? 'region' : 'tabpanel'}
            id={`main-${section}`}
            aria-label={section === 'settings' ? '设置' : undefined}
            aria-labelledby={section === 'settings' ? undefined : section}
          >
            {section === 'settings' ? (
              <SideTabWorkspace
                label="设置"
                keepMounted
                tabs={[
                  {
                    id: 'models-settings',
                    label: '工作区模型',
                    icon: <SlidersHorizontal size={18} />,
                  },
                  { id: 'appearance', label: '外观', icon: <Palette size={18} /> },
                  { id: 'connections', label: '应用联动', icon: <Link2 size={18} /> },
                ]}
              >
                {tab => (
                  <Section className="settings-page app-page">
                    <PanelHeader className="app-page-heading">
                      <h1>
                        {tab === 'appearance'
                          ? '外观'
                          : tab === 'connections'
                            ? '应用联动'
                            : '工作区模型'}
                      </h1>
                    </PanelHeader>
                    {tab === 'appearance' ? (
                      <Section className="app-flat-section grid gap-4">
                        <label className="fastui-field">
                          颜色模式
                          <Select
                            value={themeMode}
                            onChange={e =>
                              colorMode.setMode(e.target.value as 'light' | 'dark' | 'system')
                            }
                          >
                            <option value="system">跟随系统</option>
                            <option value="light">浅色</option>
                            <option value="dark">深色</option>
                          </Select>
                        </label>
                      </Section>
                    ) : tab === 'connections' ? (
                      <IntegrationStatus api={api} />
                    ) : (
                      <Section className="app-flat-section grid gap-4" aria-label="模型设置">
                        <label className="fastui-field">
                          当前使用的模型
                          <Select
                            aria-label="当前使用的模型"
                            value={`${providerId}|${model}`}
                            onChange={e => {
                              const [p, m] = e.target.value.split('|')
                              setProviderId(p)
                              setModel(m)
                            }}
                          >
                            <option value="|">请选择模型</option>
                            {modelOptions}
                          </Select>
                        </label>
                        <p className="m-0">
                          密钥仅存服务器 · 每日上限 {user.workspace?.daily_limit}
                        </p>
                        {error && <Alert tone="danger">{error}</Alert>}
                        {notice && <Alert tone="success">{notice}</Alert>}
                        {user.role === 'owner' && (
                          <form
                            className="grid gap-3"
                            onSubmit={e => {
                              e.preventDefault()
                              const f = e.currentTarget
                              const data = Object.fromEntries(new FormData(f))
                              void action(async () => {
                                await api('/providers', 'POST', {
                                  ...data,
                                  models: String(data.models)
                                    .split(/[,，]/)
                                    .map(v => v.trim())
                                    .filter(Boolean),
                                })
                                f.reset()
                                await loadProviders({ providerId, model })
                                setNotice('供应商已保存')
                              })
                            }}
                          >
                            <label className="fastui-field">
                              名称
                              <TextField name="name" required />
                            </label>
                            <label className="fastui-field">
                              API 地址
                              <TextField
                                name="base_url"
                                type="url"
                                placeholder="https://api.example.com/v1"
                                required
                              />
                            </label>
                            <label className="fastui-field">
                              API 密钥
                              <TextField
                                name="api_key"
                                type="password"
                                autoComplete="off"
                                required
                              />
                            </label>
                            <label className="fastui-field">
                              模型 ID（逗号分隔）
                              <TextField
                                name="models"
                                defaultValue="qwen3.8-27b,glm-5.2"
                                required
                              />
                            </label>
                            <Button type="submit" className="justify-self-start">
                              保存供应商
                            </Button>
                          </form>
                        )}
                      </Section>
                    )}
                  </Section>
                )}
              </SideTabWorkspace>
            ) : user.is_admin || user.role === 'admin' ? (
              <Administration api={api} currentUser={user} />
            ) : null}
          </main>
        ) : (
          <main
            className={
              deskTarget
                ? 'min-h-0 flex-1 overflow-auto xl:overflow-hidden'
                : 'min-h-0 flex-1 overflow-auto lg:overflow-hidden'
            }
            role="tabpanel"
            id="main-library"
            aria-labelledby="library"
          >
            {deskTarget ? (
              <NotebookDesk
                key={deskTarget.book_id || deskTarget.paper_id}
                target={deskTarget}
                api={api}
                action={action}
                jobs={jobs}
                providerId={providerId}
                model={model}
                onHome={home}
                onSearch={() => {
                  setImportBook(deskTarget.book_id || '')
                  setSearchReturn(deskTarget)
                  setDeskTarget(null)
                  setLibraryPage('search')
                }}
                onExternal={(id: string) => void openPaper(id)}
              />
            ) : (
              <div className="library-workbench grid min-h-full grid-cols-1 lg:h-full lg:grid-cols-[17rem_minmax(0,1fr)]">
                <WorkbenchSidebar
                  id="library-sidebar"
                  label="资料库工具"
                  tools={[
                    {
                      label: '资料库概览',
                      icon: <Files size={18} />,
                      onClick: () => {
                        setArchived(false)
                        setOffset(0)
                        home()
                      },
                      active: !archived && libraryPage === 'papers',
                    },
                    {
                      label: '归档论文',
                      icon: <Archive size={18} />,
                      onClick: () => {
                        setLibraryPage('papers')
                        setArchived(!archived)
                        setOffset(0)
                      },
                      active: archived && libraryPage === 'papers',
                    },
                    {
                      label: '后台任务',
                      icon: <ListTodo size={18} />,
                      onClick: () => {
                        setLibraryPage('jobs')
                      },
                      active: libraryPage === 'jobs',
                    },
                  ]}
                >
                  <div className="library-tree">
                    <div className="sidebar-group-heading">
                      <span>知识库</span>
                      <span>{books.length}</span>
                    </div>
                    <ActivityRail label="侧栏知识库" className="sidebar-directory">
                      {books.map(b => (
                        <Button
                          key={b.id}
                          variant="navigation"
                          className="sidebar-book"
                          onClick={() => {
                            setDeskTarget({ book_id: b.id })
                            window.history.replaceState(
                              null,
                              '',
                              APP_BASE + '?book=' + encodeURIComponent(b.id)
                            )
                          }}
                        >
                          <FolderOpen size={17} />
                          <span>{b.name}</span>
                          <ChevronRight size={13} />
                        </Button>
                      ))}
                    </ActivityRail>
                    {!books.length && <p className="sidebar-empty">将相关论文放进同一个知识库</p>}
                    <div className="sidebar-group-heading">
                      <span>{archived ? '归档论文' : '最近收入'}</span>
                      <span>{total}</span>
                    </div>
                    <ActivityRail label="论文列表" className="sidebar-directory">
                      {papers.slice(0, archived ? 20 : 6).map(p => (
                        <Button
                          variant="navigation"
                          key={p.id}
                          className="sidebar-paper"
                          title={p.title}
                          onClick={() =>
                            void action(async () => {
                              if (archived) {
                                await api(`/papers/${p.id}/restore`, 'POST')
                                await loadLibrary()
                                setNotice('论文已恢复到资料库')
                              } else await openPaper(p.id)
                            })
                          }
                        >
                          <FileText size={16} />
                          <span>{p.title}</span>
                        </Button>
                      ))}
                    </ActivityRail>
                    {archived && (
                      <Toolbar label="论文分页">
                        <Button
                          variant="quiet"
                          disabled={!offset}
                          onClick={() => setOffset(Math.max(0, offset - 20))}
                        >
                          上一页
                        </Button>
                        <span>
                          {total ? offset + 1 : 0}–{Math.min(offset + 20, total)}
                        </span>
                        <Button
                          variant="quiet"
                          disabled={offset + 20 >= total}
                          onClick={() => setOffset(offset + 20)}
                        >
                          下一页
                        </Button>
                      </Toolbar>
                    )}
                  </div>
                </WorkbenchSidebar>
                <div className="library-content min-w-0 lg:overflow-auto">
                  {libraryPage === 'jobs' ? (
                    <Jobs jobs={jobs} onRefresh={async () => setJobs((await api('/jobs')).items)} />
                  ) : libraryPage === 'search' ? (
                    <PaperSearch
                      api={api}
                      submit={submitJob}
                      jobs={jobs}
                      books={books}
                      target={importBook}
                      onTarget={setImportBook}
                      onBack={() => {
                        setLibraryPage('papers')
                        setDeskTarget(searchReturn)
                      }}
                      onJobs={() => setLibraryPage('jobs')}
                    />
                  ) : archived ? (
                    <Section className="knowledge-home archive-view app-page">
                      <div className="knowledge-hero app-page-heading">
                        <div>
                          <span className="library-breadcrumb">我的空间 / 归档</span>
                          <h1>归档论文</h1>
                          <p>暂时收起的论文，随时可以恢复到资料库。</p>
                        </div>
                      </div>
                      {!papers.length && <p className="reading-muted">暂无归档论文。</p>}
                      {papers.map(p => (
                        <div className="archive-row" key={p.id}>
                          <FileText size={20} />
                          <div>
                            <strong>{p.title}</strong>
                            <small>
                              {p.year || '年份待核实'} · {p.page_count || '—'} 页
                            </small>
                          </div>
                          <Button
                            onClick={() =>
                              void action(async () => {
                                await api(`/papers/${p.id}/restore`, 'POST')
                                await loadLibrary()
                                setNotice('论文已恢复到资料库')
                              })
                            }
                          >
                            恢复到资料库
                          </Button>
                        </div>
                      ))}
                      <Toolbar label="归档分页">
                        <Button
                          variant="quiet"
                          disabled={!offset}
                          onClick={() => setOffset(Math.max(0, offset - 20))}
                        >
                          上一页
                        </Button>
                        <span>
                          {total ? offset + 1 : 0}–{Math.min(offset + 20, total)} / {total}
                        </span>
                        <Button
                          variant="quiet"
                          disabled={offset + 20 >= total}
                          onClick={() => setOffset(offset + 20)}
                        >
                          下一页
                        </Button>
                      </Toolbar>
                    </Section>
                  ) : (
                    <Knowledge
                      key={libraryEpoch}
                      onSearch={() => {
                        setImportBook('')
                        setSearchReturn(null)
                        setLibraryPage('search')
                      }}
                      onImport={() => setLibraryDialog('import')}
                      onOpenBook={(id: string) => {
                        setDeskTarget({ book_id: id })
                        window.history.replaceState(
                          null,
                          '',
                          APP_BASE + '?book=' + encodeURIComponent(id)
                        )
                      }}
                      api={api}
                      action={action}
                      openPaper={openPaper}
                      submitJob={submitJob}
                      providerId={providerId}
                      model={model}
                      revision={jobs.map(j => `${j.id}:${j.state}`).join(',')}
                    />
                  )}
                </div>
              </div>
            )}
          </main>
        )}
        {jobs.some(j => ['queued', 'running'].includes(j.state)) && (
          <StatusBar className="app-statusbar">
            {jobs.filter(j => ['queued', 'running'].includes(j.state)).length} 个进行中的任务
          </StatusBar>
        )}
      </div>
    </OrganizeProvider>
  )
}
