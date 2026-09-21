import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import './web.css'
import './reading.css'
import Knowledge, { PaperTools } from './Knowledge'
import { OrganizeProvider, type Job } from './Organize'
import PdfReader from './PdfReader'
import Neighbors from './Neighbors'
import NotebookDesk from './NotebookDesk'
import { PanelLeft } from 'lucide-react'

type Row = Record<string, any>
let csrf = ''
const arrival = new URLSearchParams(window.location.search)
async function api(path: string, method = 'GET', body?: unknown, key?: string) {
  const headers: Record<string, string> = {}
  if (csrf) headers['X-CSRF-Token'] = csrf
  if (key) headers['Idempotency-Key'] = key
  if (body && !(body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const response = await fetch(`/api${path}`, { method, headers, credentials: 'same-origin', body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined })
  const value = await response.json()
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : '请求未通过校验')
  return value
}

export default function WebApp() {
  const [deskTarget, setDeskTarget] = useState<Row | null>(arrival.get('book') ? { book_id: arrival.get('book') } : null)
  const [user, setUser] = useState<Row | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [papers, setPapers] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [archived, setArchived] = useState(false)
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<Row | null>(null)
  const [page, setPage] = useState(1)
  const [sourceVersion, setSourceVersion] = useState('')
  const [tab, setTab] = useState('source')
  const [reports, setReports] = useState<Row[]>([])
  const [report, setReport] = useState<Row | null>(null)
  const [conversation, setConversation] = useState('')
  const [conversations, setConversations] = useState<Row[]>([])
  const [messages, setMessages] = useState<Row[]>([])
  const [summary, setSummary] = useState('')
  const [providers, setProviders] = useState<Row[]>([])
  const [providerId, setProviderId] = useState('')
  const [model, setModel] = useState('qwen3.8-27b')
  const [metadataModel, setMetadataModel] = useState('')
  const [searchResults, setSearchResults] = useState<Row | null>(null)
  const [searching, setSearching] = useState(false)
  const [settings, setSettings] = useState(false)
  const [topic, setTopic] = useState<Row | null>(null)
  const [books, setBooks] = useState<Row[]>([])
  const [importBook, setImportBook] = useState('')
  const [tagFilter, setTagFilter] = useState('')
  const [neighborTag, setNeighborTag] = useState('')
  const [importUrl, setImportUrl] = useState(arrival.get('url') || '')
  const [sidebarOpen, setSidebarOpen] = useState(() => arrival.has('url') || arrival.get('source') === 'fastnews' || arrival.has('pending') || localStorage.getItem('fastread:sidebar') === 'open')
  useEffect(() => { localStorage.setItem('fastread:sidebar', sidebarOpen ? 'open' : 'closed') }, [sidebarOpen])
  useEffect(() => { const close = (e: KeyboardEvent) => { if (e.key === 'Escape') setSidebarOpen(false) }; window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close) }, [])

  async function action(fn: () => Promise<unknown>) {
    setError(''); setNotice('')
    try { return await fn() } catch (e) { setError((e as Error).message) }
  }
  async function loadLibrary() {
    const data = await api(`/papers?limit=20&offset=${offset}&archived=${archived}`)
    setPapers(data.items); setTotal(data.total)
    setBooks((await api('/knowledge-bases')).items)
  }
  async function loadProviders() {
    const data = await api('/providers'); setProviders(data.items)
    if (data.items.length && !providerId) {
      setProviderId(data.items[0].id); setModel(data.items[0].models[0])
      const qwen = data.items.flatMap((p: Row) => p.models.map((m: string) => ({ provider: p.id, model: m }))).find((v: Row) => /qwen/i.test(v.model) && /27b/i.test(v.model))
      if (qwen) setMetadataModel(`${qwen.provider}|${qwen.model}`)
    }
  }
  async function loadReports(id: string) {
    const data = await api(`/papers/${id}/reports`); setReports(data.items)
    const current = data.items.find((r: Row) => r.version_id === data.active_version)
    setReport(current ? await api(`/papers/${id}/reports/${current.id}`) : null)
  }
  async function openPaper(id: string, targetPage?: number, targetVersion?: string) {
    if (selected && summary !== selected.summary && !window.confirm('阅读笔记尚未保存，草稿已暂存本机。仍要切换论文？')) return
    setTopic(null)
    setNeighborTag('')
    setSearchResults(null)
    if (window.innerWidth < 800) setSidebarOpen(false)
    const data = await api(`/papers/${id}`)
    setSelected(data); setSourceVersion(targetVersion || data.active_version); setSummary(data.summary); setTab('source')
    setPage(targetPage || Math.min(data.metadata.page_count || 1, Math.max(1, Number(localStorage.getItem(`reading:${user?.workspace_id}:${id}`)) || 1)))
    const conv = await api(`/papers/${id}/conversations`, 'POST')
    setConversation(conv.id)
    setConversations((await api(`/papers/${id}/conversations`)).items)
    setMessages((await api(`/conversations/${conv.id}/messages`)).items)
    await loadReports(id)
    setDeskTarget({ paper_id: id, page: targetPage, version: targetVersion }); window.history.replaceState(null, '', '/?paper=' + encodeURIComponent(id))
  }
  useEffect(() => { api('/auth/me').then(data => { csrf = data.csrf; setUser(data) }).catch(() => {}).finally(() => setLoading(false)) }, [])
  useEffect(() => { if (user) void action(async () => { await loadLibrary(); await loadProviders() }) }, [user, offset, archived])
  useEffect(() => { if (user && arrival.get('paper')) void action(() => openPaper(arrival.get('paper')!)); if (user && arrival.get('job')) void action(async () => { const job = await api('/jobs/' + encodeURIComponent(arrival.get('job')!)); if (job.result?.paper_id) await openPaper(job.result.paper_id) }) }, [user])
  useEffect(() => {
    if (!selected) return
    localStorage.setItem(`reading:${user?.workspace_id}:${selected.id}`, String(page))
  }, [selected?.id, page, sourceVersion])
  useEffect(() => {
    if (!user) return
    let stopped = false
    let previous = ''
    async function refresh() {
      try {
        const data = await api('/jobs'); if (stopped) return
        setJobs(data.items)
        const completed = data.items.filter((j: Row) => j.state === 'succeeded').map((j: Row) => j.id).join(',')
        if (completed !== previous) {
          previous = completed; await loadLibrary()
          if (selected) { await loadReports(selected.id); setSelected(await api(`/papers/${selected.id}`)) }
          if (conversation) setMessages((await api(`/conversations/${conversation}/messages`)).items)
        }
      } catch (e) { if (!stopped) setError((e as Error).message) }
    }
    void refresh(); const timer = setInterval(refresh, 3000)
    return () => { stopped = true; clearInterval(timer) }
  }, [user, selected?.id, conversation, offset, archived])

  async function submitJob(path: string, body?: unknown) {
    if (path.startsWith('/imports/')) {
      if (body instanceof FormData) body.set('knowledge_id', importBook)
      else body = { ...(body as Row), knowledge_id: importBook }
    }
    if (path.startsWith('/imports/') && metadataModel) {
      const [provider_id, model] = metadataModel.split('|')
      if (body instanceof FormData) { body.set('provider_id', provider_id); body.set('model', model) }
      else body = { ...(body as Row), provider_id, model }
    }
    const job = await api(path, 'POST', body, crypto.randomUUID())
    setJobs(current => [job, ...current.filter(j => j.id !== job.id)])
    setNotice(path.endsWith('/organize') ? '' : '任务已交给服务器，关闭网页后仍会继续。')
    return job
  }
  if (loading) return <div className="web-center">正在连接资料库…</div>
  if (!user) return <main className="web-login"><div className="wordmark">FastRead</div><h1>正在连接共享资料库</h1><p>暂时无法连接服务，请稍后重试。</p><button onClick={() => window.location.reload()}>重新连接</button></main>

  return (<OrganizeProvider jobs={jobs} submit={submitJob} api={api}><div className={`web-shell ${(sidebarOpen ? "sidebar-open" : "sidebar-closed") + (deskTarget ? " desk-mode" : "")}`}><header><button className="sidebar-toggle quiet" aria-label={sidebarOpen ? "收起左边栏" : "展开左边栏"} title={sidebarOpen ? "收起左边栏" : "展开左边栏"} aria-expanded={sidebarOpen} aria-controls={deskTarget ? "desk-sources" : "library-sidebar"} onClick={() => setSidebarOpen(!sidebarOpen)}><PanelLeft size={22} strokeWidth={1.7} /></button><button className="wordmark quiet" onClick={() => { setSelected(null); setTopic(null); setSearchResults(null); setTagFilter(''); setDeskTarget(null); window.history.replaceState(null, '', '/') }}>FastRead <span>KNOWLEDGE</span></button><span className="workspace-name">{user.workspace.name}</span><div className="header-actions"><button className="quiet" onClick={() => setSettings(!settings)}>模型设置</button><span>{user.public ? "共享资料库" : user.email}</span>{!user.public && <button className="quiet" onClick={() => void action(async () => { await api('/auth/logout', 'POST'); csrf = ''; setUser(null); setSelected(null); setMessages([]); setPapers([]); setJobs([]) })}>退出登录</button>}</div></header>
    {error && <div className="error banner" role="alert">{error}<button className="quiet" onClick={() => setError('')}>关闭</button></div>}
    {notice && <div role="status" className="notice banner">{notice}</div>}
    {settings && <section className="settings"><h2>工作区模型</h2><label>当前使用的模型<select aria-label="当前使用的模型" value={`${providerId}|${model}`} onChange={e => { const [p,m] = e.target.value.split('|'); setProviderId(p); setModel(m) }}>{providers.flatMap(p => p.models.map((m: string) => <option key={`${p.id}|${m}`} value={`${p.id}|${m}`}>{m} · {p.name}</option>))}</select></label><p>供应商密钥仅保存在服务器，其他设备登录后可继续使用。当前 24 小时任务上限：{user.workspace.daily_limit}。</p>{providers.map(p => <p key={p.id}>{p.name} · {p.models.join(' / ')}</p>)}
      {user.role === 'owner' && <form onSubmit={e => { e.preventDefault(); const f = e.currentTarget; const data = Object.fromEntries(new FormData(f)); void action(async () => { await api('/providers', 'POST', { ...data, models: String(data.models).split(',').map(v => v.trim()) }); f.reset(); await loadProviders(); setNotice('供应商已保存') }) }}>
        <label>名称<input name="name" required /></label><label>API 地址<input name="base_url" type="url" placeholder="https://api.example.com/v1" required /></label><label>API 密钥<input name="api_key" type="password" autoComplete="off" required /></label><label>模型 ID（逗号分隔）<input name="models" defaultValue="qwen3.8-27b,glm-5.2" required /></label><button>保存供应商</button>
      </form>}</section>}
    <div className="web-columns">{sidebarOpen && <button className="sidebar-backdrop" aria-label="关闭资料库抽屉" onClick={() => setSidebarOpen(false)} />}<aside id="library-sidebar" inert={!sidebarOpen}><div className="section-heading"><h2>{archived ? '已归档' : '资料库'}</h2><span>{total} 篇</span><button className="quiet" onClick={() => { setArchived(!archived); setOffset(0); setSelected(null) }}>{archived ? '返回资料库' : '查看归档'}</button></div><form className="search" onSubmit={e => { e.preventDefault(); const query = String(new FormData(e.currentTarget).get('query')); setSearching(true); void action(async () => setSearchResults(await api('/search', 'POST', { query }))).finally(() => setSearching(false)) }}><label>搜索公开论文<input name="query" placeholder="论文标题、DOI 或关键词" required /></label><button disabled={searching}>{searching ? '搜索中…' : '搜索'}</button></form>
      <label>导入时识别标题与作者<select aria-label="元数据模型" value={metadataModel} onChange={e => setMetadataModel(e.target.value)}><option value="">版面识别与公开索引核验</option>{providers.flatMap(p => p.models.map((m: string) => <option key={p.id + '|' + m} value={p.id + '|' + m}>{m} · {p.name}</option>))}</select></label>{metadataModel && <small>第一页文本将交给所选模型，计入工作区模型任务额度。</small>}
      <button className="home-nav" onClick={() => { setSelected(null); setTopic(null); setSearchResults(null) }}>▦ 知识库与关系矩阵</button><details className="import-box" open={arrival.has("url") || arrival.get("source") === "fastnews" || arrival.has("pending") || undefined}><summary>导入论文</summary>{arrival.get("source") === "fastnews" && <p className="notice">{arrival.get("title") ? `来自 FastNews，已收入「${arrival.get("title")}」。请自行上传 PDF。` : "来自 FastNews，请自行上传 PDF。"}</p>}<label>导入后归入<select aria-label="导入知识库" value={importBook} onChange={e => setImportBook(e.target.value)}><option value="">AI 自动归入知识库</option>{books.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label><form onSubmit={e => { e.preventDefault(); const url = String(new FormData(e.currentTarget).get('url')); void action(() => submitJob('/imports/url', { url, knowledge_id: importBook, source: arrival.get('source') || '', external_id: arrival.get('external_id') || '' })) }}><label>论文链接<input name="url" value={importUrl} onChange={e => setImportUrl(e.target.value)} type="url" placeholder="https://arxiv.org/pdf/…" required /></label><button>导入链接</button></form><label className="file-button">上传 PDF<input aria-label="上传 PDF" type="file" accept="application/pdf" onChange={e => { const file = e.target.files?.[0]; if (!file) return; const data = new FormData(); data.set('file', file); data.set('knowledge_id', importBook); if (arrival.get('pending')) data.set('paper_id', arrival.get('pending')!); void action(() => submitJob('/imports/pdf', data)); e.target.value = '' }} /></label></details>
      <nav className="paper-list">{papers.map(p => <button key={p.id} className={selected?.id === p.id ? 'paper active' : 'paper'} onClick={() => void action(async () => { if (archived) { await api(`/papers/${p.id}/restore`, 'POST'); await loadLibrary(); setNotice('论文已恢复到资料库') } else await openPaper(p.id) })}><strong>{p.title}</strong>{archived && <span>点击恢复到资料库</span>}<span>{p.year || '年份待核实'} · {p.page_count} 页</span></button>)}</nav><div className="pagination"><button className="quiet" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>上一页</button><span>{offset + 1}–{Math.min(offset + 20, total)}</span><button className="quiet" disabled={offset + 20 >= total} onClick={() => setOffset(offset + 20)}>下一页</button></div>
    </aside><main className="reading-main">
      {deskTarget ? <NotebookDesk key={deskTarget.book_id || deskTarget.paper_id} target={deskTarget} api={api} action={action} jobs={jobs} providerId={providerId} model={model} sidebarOpen={sidebarOpen} onHome={() => { setDeskTarget(null); setSelected(null); window.history.replaceState(null, '', '/') }} onExternal={(id: string) => { setDeskTarget({ paper_id: id }); window.history.replaceState(null, '', '/?paper=' + encodeURIComponent(id)) }} /> : searchResults ? <section className="search-results"><div className="section-heading"><h1>搜索结果</h1><button className="quiet" onClick={() => setSearchResults(null)}>返回阅读</button></div><p>公开来源：{Object.entries(searchResults.sources || {}).map(([name, status]) => `${name} ${(status as Row).available ? '可用' : (status as Row).reason || '暂不可用'}`).join(' · ')}</p>{searchResults.papers.map((p: Row, i: number) => <article key={p.id || i}><h2>{p.title}</h2><p>{p.authors?.join(', ')} · {p.year || '年份待核实'}</p><small>{(p.discovery_sources || []).join(' / ')}{p.doi ? ` · DOI: ${p.doi}` : ''}</small>{p.identity_warning && <p role="note">{p.identity_warning}</p>}<p>{p.abstract?.slice(0, 500)}</p><div className="toolbar">{(p.pdf_url || p.url || p.source_url) && <a href={p.pdf_url || p.url || p.source_url} target="_blank" rel="noreferrer">查看来源</a>}<button onClick={() => void action(() => submitJob('/imports/url', { url: p.pdf_url || p.url || p.source_url || `https://doi.org/${p.doi}` }))}>导入这篇论文</button></div></article>)}</section> : topic ? <section><div className="section-heading"><h1>{topic.question}</h1><button className="quiet" onClick={() => setTopic(null)}>返回阅读</button></div><p>{topic.scope}</p><h2>专题证据</h2>{topic.evidence.map((e: Row) => <article key={e.id}><blockquote>第 {e.page} 页 · {e.quote}</blockquote><p>{e.note}</p><small>{e.location_status === 'located' ? '逐字引文已在迁移原文定位' : '原文定位待复核'}</small></article>)}</section> : !selected ? <Knowledge onOpenBook={(id: string) => { setDeskTarget({ book_id: id }); if(window.innerWidth > 900) setSidebarOpen(true); window.history.replaceState(null, '', '/?book=' + encodeURIComponent(id)) }} api={api} action={action} openPaper={openPaper} submitJob={submitJob} providerId={providerId} model={model} revision={jobs.map(j => `${j.id}:${j.state}`).join(',')} initialTag={tagFilter} /> : <>
        <div className="paper-heading"><div className="eyebrow">PAPER WORKSPACE</div><h1>{selected.title}</h1><p>{selected.metadata.authors?.join(', ')}</p>{selected.metadata.metadata_resolution?.status && <small>{selected.metadata.metadata_resolution.status === 'registry_verified' ? '标题与标识已匹配公开索引' : '元数据尚未获得公开索引核验'} · {selected.metadata.metadata_resolution.model_status === 'source_located' ? '模型抽取已定位原文，语义仍需核对' : selected.metadata.metadata_resolution.model_status === 'failed_or_rejected' ? '模型抽取失败，已使用版面与索引结果' : '未使用模型抽取'}</small>}<div className="toolbar"><span>{selected.metadata.page_count} 页</span><button className="quiet" onClick={() => void action(async () => { await api(`/papers/${selected.id}`, 'DELETE'); setSelected(null); await loadLibrary(); setNotice('论文已归档，可在归档列表恢复') })}>归档论文</button><label>模型<select aria-label="选择模型" value={`${providerId}|${model}`} onChange={e => { const [p, m] = e.target.value.split('|'); setProviderId(p); setModel(m) }}><option value="|">配置模型后生成</option>{providers.flatMap(p => p.models.map((m: string) => <option key={`${p.id}|${m}`} value={`${p.id}|${m}`}>{m} · {p.name}</option>))}</select></label><a href={`/api/papers/${selected.id}/export`} download>导出 Markdown</a><button className="quiet" onClick={() => setTab("neighbors")}>近邻筛选</button></div></div>
        <details className="paper-details"><summary>论文原理、标签与知识库</summary><PaperTools paper={selected} books={books} api={api} action={action} openPaper={openPaper} submitJob={submitJob} providerId={providerId} model={model} revision="" onTag={tag => { setNeighborTag(tag); setTab('neighbors') }} reload={async () => { setSelected(await api(`/papers/${selected.id}`)); await loadLibrary() }} /></details>
        <nav className="tabs">{[['source', '阅读与批注'], ['report', '阅读报告'], ['chat', '持续追问'], ['neighbors', '近邻论文']].map(([id, title]) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{title}</button>)}</nav>
        {tab === 'source' && <section className="source"><details className="source-versions"><summary>文档版本</summary><select aria-label="原文版本" value={sourceVersion} onChange={e => { setSourceVersion(e.target.value); setPage(1) }}>{selected.versions.map((v: Row) => <option key={v.id} value={v.id}>{new Date(v.created * 1000).toLocaleString()}{v.id === selected.active_version ? '（当前）' : ''}</option>)}</select></details><PdfReader key={selected.id} paper={selected} version={sourceVersion} page={page} setPage={setPage} api={api} summary={summary} setSummary={setSummary} onSaved={s => setSelected(current => current ? { ...current, summary: s } : current)} /></section>}
        {tab === 'report' && <section className="report"><div className="toolbar"><button disabled={!providerId || jobs.some(j => j.kind === 'report' && j.resource_id === selected.id && ['queued','running'].includes(j.state))} onClick={() => void action(() => submitJob(`/papers/${selected.id}/reports`, { provider_id: providerId, model }))}>{report ? '生成新版报告' : '生成阅读报告'}</button><select aria-label="报告版本" value={report?.id || ''} onChange={e => void action(async () => setReport(await api(`/papers/${selected.id}/reports/${e.target.value}`)))}><option value="" disabled>选择历史版本</option>{reports.map(r => <option key={r.id} value={r.id}>{new Date(r.created * 1000).toLocaleString()}</option>)}</select></div>{!report ? <p>报告会涵盖关键问题、方法过程、主要贡献和原文证据。</p> : <><p className="evidence-note">{report.stale ? '此报告属于旧文档版本。' : ''}页码与逐字引文已校验；引用存在本身不等于结论已获独立验证。</p>{['key_questions', 'process', 'contributions'].map(section => <div key={section}><h2>{{ key_questions: '关键问题', process: '方法过程', contributions: '主要贡献' }[section]}</h2>{report.content[section]?.map((item: Row, i: number) => <article key={i}><h3>{item.question || item.step || item.title}</h3><ReactMarkdown>{item.answer || item.description || ''}</ReactMarkdown>{item.evidence?.map((ev: Row, n: number) => <blockquote key={n}><button className="page-link" onClick={() => { setSourceVersion(report.version_id); setPage(ev.page_start || ev.page || 1); setTab('source') }}>第 {ev.page_start || ev.page} 页</button> {ev.exact_quote}</blockquote>)}</article>)}</div>)}<h2>局限</h2><ul>{report.content.limitations?.map((v: string, i: number) => <li key={i}>{v}</li>)}</ul></>}</section>}
        {tab === 'chat' && <section className="chat"><label>对话版本<select aria-label="对话版本" value={conversation} onChange={e => { const id = e.target.value; setConversation(id); void action(async () => setMessages((await api(`/conversations/${id}/messages`)).items)) }}>{conversations.map(c => <option key={c.id} value={c.id}>{new Date(c.created * 1000).toLocaleString()}{c.version_id === selected.active_version ? '（当前原文）' : '（历史原文）'}</option>)}</select></label><div className="messages">{messages.map(m => <article key={m.id} className={`message ${m.role}`}><b>{m.role === 'user' ? '你' : 'FastRead'}</b><ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{m.content}</ReactMarkdown>{m.role === 'assistant' && m.evidence.grounding_detail && <p className="evidence-note">{m.evidence.grounding_detail}</p>}{m.evidence.sources?.map((ev: Row, i: number) => <blockquote key={i}><button className="page-link" onClick={() => { setSourceVersion(ev.document_version_id || selected.active_version); setPage(ev.page_start); setTab('source') }}>第 {ev.page_start} 页</button> {ev.exact_quote}</blockquote>)}</article>)}</div><form onSubmit={e => { e.preventDefault(); const form = e.currentTarget; const content = String(new FormData(form).get('question')); void action(async () => { await submitJob(`/conversations/${conversation}/messages`, { content, provider_id: providerId, model }); form.reset(); setMessages((await api(`/conversations/${conversation}/messages`)).items) }) }}><label>继续追问<textarea name="question" placeholder="这篇论文的方法与基线有什么不同？请引用原文。" required maxLength={10000} /></label><button disabled={!providerId || jobs.some(j => j.kind === 'chat' && j.resource_id === conversation && ['queued','running'].includes(j.state))}>发送问题</button></form></section>}
        {tab === 'neighbors' && <Neighbors key={selected.id} initialTag={neighborTag} paper={selected} api={api} action={action} openPaper={openPaper} submitJob={submitJob} revision={jobs.filter(j => j.kind === 'neighbors' && j.state === 'succeeded').map(j => j.id).join(',')} pending={jobs.some(j => j.kind === 'neighbors' && j.resource_id === selected.id && ['queued','running'].includes(j.state))} />}
      </>}
    </main></div></div></OrganizeProvider>
  )
}
