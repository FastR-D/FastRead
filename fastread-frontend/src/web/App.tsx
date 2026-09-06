import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import './web.css'

type Row = Record<string, any>
let csrf = ''
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
const labels: Record<string, string> = { queued: '排队中', running: '处理中', succeeded: '已完成', failed: '失败', needs_attention: '执行结果待确认', cancelled: '已取消', import_url: '导入论文', import_pdf: '解析 PDF', report: '阅读报告', chat: '回答问题', index: '重建索引', neighbors: '近邻论文' }

export default function WebApp() {
  const [user, setUser] = useState<Row | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [papers, setPapers] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [archived, setArchived] = useState(false)
  const [jobs, setJobs] = useState<Row[]>([])
  const [selected, setSelected] = useState<Row | null>(null)
  const [page, setPage] = useState(1)
  const [pageText, setPageText] = useState('')
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
  const [searchResults, setSearchResults] = useState<Row | null>(null)
  const [searching, setSearching] = useState(false)
  const [settings, setSettings] = useState(false)
  const [topics, setTopics] = useState<Row[]>([])
  const [topic, setTopic] = useState<Row | null>(null)

  async function action(fn: () => Promise<unknown>) {
    setError(''); setNotice('')
    try { return await fn() } catch (e) { setError((e as Error).message) }
  }
  async function loadLibrary() {
    const data = await api(`/papers?limit=20&offset=${offset}&archived=${archived}`)
    setPapers(data.items); setTotal(data.total)
    setTopics((await api('/topics')).items)
  }
  async function loadProviders() {
    const data = await api('/providers'); setProviders(data.items)
    if (data.items.length && !providerId) {
      setProviderId(data.items[0].id); setModel(data.items[0].models[0])
    }
  }
  async function loadReports(id: string) {
    const data = await api(`/papers/${id}/reports`); setReports(data.items)
    const current = data.items.find((r: Row) => r.version_id === data.active_version)
    setReport(current ? await api(`/papers/${id}/reports/${current.id}`) : null)
  }
  async function openPaper(id: string) {
    setTopic(null)
    const data = await api(`/papers/${id}`)
    setSelected(data); setSourceVersion(data.active_version); setSummary(data.summary); setTab('source')
    setPage(Math.min(data.metadata.page_count || 1, Math.max(1, Number(localStorage.getItem(`reading:${user?.workspace_id}:${id}`)) || 1)))
    const conv = await api(`/papers/${id}/conversations`, 'POST')
    setConversation(conv.id)
    setConversations((await api(`/papers/${id}/conversations`)).items)
    setMessages((await api(`/conversations/${conv.id}/messages`)).items)
    await loadReports(id)
  }
  useEffect(() => { api('/auth/me').then(data => { csrf = data.csrf; setUser(data) }).catch(() => {}).finally(() => setLoading(false)) }, [])
  useEffect(() => { if (user) void action(async () => { await loadLibrary(); await loadProviders() }) }, [user, offset, archived])
  useEffect(() => {
    if (!selected) return
    setPageText('加载中…')
    let active = true
    api(`/papers/${selected.id}/pages/${page}?version=${sourceVersion || selected.active_version}`).then(data => { if (active) setPageText(data.text) }).catch(e => { if (active) setError(e.message) })
    localStorage.setItem(`reading:${user?.workspace_id}:${selected.id}`, String(page))
    return () => { active = false }
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
          if (selected) await loadReports(selected.id)
          if (conversation) setMessages((await api(`/conversations/${conversation}/messages`)).items)
        }
      } catch (e) { if (!stopped) setError((e as Error).message) }
    }
    void refresh(); const timer = setInterval(refresh, 3000)
    return () => { stopped = true; clearInterval(timer) }
  }, [user, selected?.id, conversation, offset, archived])

  async function submitJob(path: string, body?: unknown) {
    const job = await api(path, 'POST', body, crypto.randomUUID())
    setJobs(current => [job, ...current.filter(j => j.id !== job.id)])
    setNotice('任务已交给服务器，关闭网页后仍会继续。')
  }
  const sourcePageCount = selected?.versions.find((v: Row) => v.id === sourceVersion)?.page_count || selected?.metadata.page_count || 1
  if (loading) return <div className="web-center">正在连接资料库…</div>
  if (!user) return <main className="web-login"><div className="wordmark">FastRead <span>WEB</span></div><h1>让阅读留下可追溯的理解</h1><p>登录你的资料库，继续论文、报告与对话。</p><form onSubmit={e => { e.preventDefault(); const form = new FormData(e.currentTarget); void action(async () => { await api('/auth/login', 'POST', Object.fromEntries(form)); const me = await api('/auth/me'); csrf = me.csrf; setUser(me) }) }}>
    <label>邮箱<input name="email" type="email" autoComplete="username" required /></label><label>密码<input name="password" type="password" autoComplete="current-password" required /></label><button>登录</button>
  </form>{error && <p role="alert" className="error">{error}</p>}<small>账户由服务管理员开通。</small></main>

  return (<div className="web-shell"><header><div className="wordmark">FastRead <span>WEB</span></div><span className="workspace-name">{user.workspace.name}</span><div className="header-actions"><button className="quiet" onClick={() => setSettings(!settings)}>模型设置</button><span>{user.email}</span><button className="quiet" onClick={() => void action(async () => { await api('/auth/logout', 'POST'); csrf = ''; setUser(null); setSelected(null); setMessages([]); setPapers([]); setJobs([]) })}>退出登录</button></div></header>
    {error && <div className="error banner" role="alert">{error}<button className="quiet" onClick={() => setError('')}>关闭</button></div>}
    {notice && <div role="status" className="notice banner">{notice}</div>}
    {settings && <section className="settings"><h2>工作区模型</h2><p>供应商密钥仅保存在服务器，其他设备登录后可继续使用。当前 24 小时任务上限：{user.workspace.daily_limit}。</p>{providers.map(p => <p key={p.id}>{p.name} · {p.models.join(' / ')}</p>)}
      {user.role === 'owner' && <form onSubmit={e => { e.preventDefault(); const f = e.currentTarget; const data = Object.fromEntries(new FormData(f)); void action(async () => { await api('/providers', 'POST', { ...data, models: String(data.models).split(',').map(v => v.trim()) }); f.reset(); await loadProviders(); setNotice('供应商已保存') }) }}>
        <label>名称<input name="name" required /></label><label>API 地址<input name="base_url" type="url" placeholder="https://api.example.com/v1" required /></label><label>API 密钥<input name="api_key" type="password" autoComplete="off" required /></label><label>模型 ID（逗号分隔）<input name="models" defaultValue="qwen3.8-27b,glm-5.2" required /></label><button>保存供应商</button>
      </form>}</section>}
    <div className="web-columns"><aside><div className="section-heading"><h2>{archived ? '已归档' : '资料库'}</h2><span>{total} 篇</span><button className="quiet" onClick={() => { setArchived(!archived); setOffset(0); setSelected(null) }}>{archived ? '返回资料库' : '查看归档'}</button></div><form className="search" onSubmit={e => { e.preventDefault(); const query = String(new FormData(e.currentTarget).get('query')); setSearching(true); void action(async () => setSearchResults(await api('/search', 'POST', { query }))).finally(() => setSearching(false)) }}><label>搜索公开论文<input name="query" placeholder="论文标题、DOI 或关键词" required /></label><button disabled={searching}>{searching ? '搜索中…' : '搜索'}</button></form>
      <details className="import-box"><summary>导入论文</summary><form onSubmit={e => { e.preventDefault(); const url = String(new FormData(e.currentTarget).get('url')); void action(() => submitJob('/imports/url', { url })) }}><label>论文链接<input name="url" type="url" placeholder="https://arxiv.org/pdf/…" required /></label><button>导入链接</button></form><label className="file-button">上传 PDF<input aria-label="上传 PDF" type="file" accept="application/pdf" onChange={e => { const file = e.target.files?.[0]; if (!file) return; const data = new FormData(); data.set('file', file); void action(() => submitJob('/imports/pdf', data)); e.target.value = '' }} /></label></details>
      <nav className="paper-list">{papers.map(p => <button key={p.id} className={selected?.id === p.id ? 'paper active' : 'paper'} onClick={() => void action(async () => { if (archived) { await api(`/papers/${p.id}/restore`, 'POST'); await loadLibrary(); setNotice('论文已恢复到资料库') } else await openPaper(p.id) })}><strong>{p.title}</strong>{archived && <span>点击恢复到资料库</span>}<span>{p.year || '年份待核实'} · {p.page_count} 页</span></button>)}</nav><div className="pagination"><button className="quiet" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>上一页</button><span>{offset + 1}–{Math.min(offset + 20, total)}</span><button className="quiet" disabled={offset + 20 >= total} onClick={() => setOffset(offset + 20)}>下一页</button></div>
      <details className="job-list"><summary>研究专题（{topics.length}）</summary>{topics.map(t => <button key={t.id} className="paper" onClick={() => void action(async () => { setTopic(await api(`/topics/${t.id}`)); setSearchResults(null) })}>{t.question}</button>)}</details><details className="job-list" open><summary>后台任务</summary>{jobs.slice(0, 15).map(j => <div key={j.id} className="job"><div><b>{labels[j.kind]}</b><span className={`state ${j.state}`}>{labels[j.state]}</span></div>{j.error && <small>{j.error}</small>}{j.kind.startsWith('import') && j.state === 'succeeded' && <button className="quiet" onClick={() => void action(() => openPaper(j.result.paper_id))}>打开论文</button>}{j.kind === 'neighbors' && j.state === 'succeeded' && <button className="quiet" onClick={() => setSearchResults(j.result)}>查看近邻</button>}</div>)}</details>
    </aside><main className="reading-main">
      {searchResults ? <section className="search-results"><div className="section-heading"><h1>搜索结果</h1><button className="quiet" onClick={() => setSearchResults(null)}>返回阅读</button></div><p>公开来源：{Object.entries(searchResults.sources || {}).map(([name, status]) => `${name} ${(status as Row).available ? '可用' : (status as Row).reason || '暂不可用'}`).join(' · ')}</p>{searchResults.papers.map((p: Row, i: number) => <article key={p.id || i}><h2>{p.title}</h2><p>{p.authors?.join(', ')} · {p.year || '年份待核实'}</p><small>{(p.discovery_sources || []).join(' / ')}</small><p>{p.abstract?.slice(0, 500)}</p><div className="toolbar">{(p.pdf_url || p.url || p.source_url) && <a href={p.pdf_url || p.url || p.source_url} target="_blank" rel="noreferrer">查看来源</a>}<button onClick={() => void action(() => submitJob('/imports/url', { url: p.pdf_url || p.url || p.source_url || `https://doi.org/${p.doi}` }))}>导入这篇论文</button></div></article>)}</section> : topic ? <section><div className="section-heading"><h1>{topic.question}</h1><button className="quiet" onClick={() => setTopic(null)}>返回阅读</button></div><p>{topic.scope}</p><h2>专题证据</h2>{topic.evidence.map((e: Row) => <article key={e.id}><blockquote>第 {e.page} 页 · {e.quote}</blockquote><p>{e.note}</p><small>{e.location_status === 'located' ? '逐字引文已在迁移原文定位' : '原文定位待复核'}</small></article>)}</section> : !selected ? <section className="empty"><div className="eyebrow">YOUR RESEARCH, CONTINUED</div><h1>从一篇论文开始</h1><p>搜索或导入 PDF，检查分页原文，生成阅读报告，再沿着证据继续追问。</p><div className="steps"><div><b>01</b><h3>找到原文</h3><p>分页阅读，保留来源。</p></div><div><b>02</b><h3>建立理解</h3><p>问题、方法、贡献与引文。</p></div><div><b>03</b><h3>持续追问</h3><p>对话与总结跨设备保存。</p></div></div></section> : <>
        <div className="paper-heading"><div className="eyebrow">PAPER WORKSPACE</div><h1>{selected.title}</h1><p>{selected.metadata.authors?.join(', ')}</p><div className="toolbar"><span>{selected.metadata.page_count} 页</span><button className="quiet" onClick={() => void action(async () => { await api(`/papers/${selected.id}`, 'DELETE'); setSelected(null); await loadLibrary(); setNotice('论文已归档，可在归档列表恢复') })}>归档论文</button><label>模型<select aria-label="选择模型" value={`${providerId}|${model}`} onChange={e => { const [p, m] = e.target.value.split('|'); setProviderId(p); setModel(m) }}><option value="|">配置模型后生成</option>{providers.flatMap(p => p.models.map((m: string) => <option key={`${p.id}|${m}`} value={`${p.id}|${m}`}>{m} · {p.name}</option>))}</select></label><a href={`/api/papers/${selected.id}/export`} download>导出 Markdown</a><button className="quiet" onClick={() => void action(() => submitJob(`/papers/${selected.id}/neighbors`))}>发现近邻</button></div></div>
        <nav className="tabs">{[['source', '分页原文'], ['report', '阅读报告'], ['chat', '持续追问'], ['summary', '个人总结']].map(([id, title]) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{title}</button>)}</nav>
        {tab === 'source' && <section className="source"><div className="toolbar"><label>原文版本<select aria-label="原文版本" value={sourceVersion} onChange={e => { setSourceVersion(e.target.value); setPage(1) }}>{selected.versions.map((v: Row) => <option key={v.id} value={v.id}>{new Date(v.created * 1000).toLocaleString()}{v.id === selected.active_version ? '（当前）' : ''}</option>)}</select></label><button className="quiet" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button><label>页码<input aria-label="页码" type="number" min={1} max={sourcePageCount} value={page} onChange={e => setPage(Math.max(1, Math.min(sourcePageCount, Number(e.target.value) || 1)))} /></label><button className="quiet" disabled={page >= sourcePageCount} onClick={() => setPage(page + 1)}>下一页</button><a href={`/api/papers/${selected.id}/file?version=${sourceVersion}`} target="_blank" rel="noreferrer">打开原版 PDF</a></div><pre className="page-text">{pageText}</pre></section>}
        {tab === 'report' && <section className="report"><div className="toolbar"><button disabled={!providerId || jobs.some(j => j.kind === 'report' && j.resource_id === selected.id && ['queued','running'].includes(j.state))} onClick={() => void action(() => submitJob(`/papers/${selected.id}/reports`, { provider_id: providerId, model }))}>{report ? '生成新版报告' : '生成阅读报告'}</button><select aria-label="报告版本" value={report?.id || ''} onChange={e => void action(async () => setReport(await api(`/papers/${selected.id}/reports/${e.target.value}`)))}><option value="" disabled>选择历史版本</option>{reports.map(r => <option key={r.id} value={r.id}>{new Date(r.created * 1000).toLocaleString()}</option>)}</select></div>{!report ? <p>报告会涵盖关键问题、方法过程、主要贡献和原文证据。</p> : <><p className="evidence-note">{report.stale ? '此报告属于旧文档版本。' : ''}页码与逐字引文已校验；引用存在本身不等于结论已获独立验证。</p>{['key_questions', 'process', 'contributions'].map(section => <div key={section}><h2>{{ key_questions: '关键问题', process: '方法过程', contributions: '主要贡献' }[section]}</h2>{report.content[section]?.map((item: Row, i: number) => <article key={i}><h3>{item.question || item.step || item.title}</h3><ReactMarkdown>{item.answer || item.description || ''}</ReactMarkdown>{item.evidence?.map((ev: Row, n: number) => <blockquote key={n}><button className="page-link" onClick={() => { setSourceVersion(report.version_id); setPage(ev.page_start || ev.page || 1); setTab('source') }}>第 {ev.page_start || ev.page} 页</button> {ev.exact_quote}</blockquote>)}</article>)}</div>)}<h2>局限</h2><ul>{report.content.limitations?.map((v: string, i: number) => <li key={i}>{v}</li>)}</ul></>}</section>}
        {tab === 'chat' && <section className="chat"><label>对话版本<select aria-label="对话版本" value={conversation} onChange={e => { const id = e.target.value; setConversation(id); void action(async () => setMessages((await api(`/conversations/${id}/messages`)).items)) }}>{conversations.map(c => <option key={c.id} value={c.id}>{new Date(c.created * 1000).toLocaleString()}{c.version_id === selected.active_version ? '（当前原文）' : '（历史原文）'}</option>)}</select></label><div className="messages">{messages.map(m => <article key={m.id} className={`message ${m.role}`}><b>{m.role === 'user' ? '你' : 'FastRead'}</b><ReactMarkdown>{m.content}</ReactMarkdown>{m.evidence.sources?.map((ev: Row, i: number) => <blockquote key={i}><button className="page-link" onClick={() => { setSourceVersion(ev.document_version_id || selected.active_version); setPage(ev.page_start); setTab('source') }}>第 {ev.page_start} 页</button> {ev.exact_quote}</blockquote>)}</article>)}</div><form onSubmit={e => { e.preventDefault(); const form = e.currentTarget; const content = String(new FormData(form).get('question')); void action(async () => { await submitJob(`/conversations/${conversation}/messages`, { content, provider_id: providerId, model }); form.reset(); setMessages((await api(`/conversations/${conversation}/messages`)).items) }) }}><label>继续追问<textarea name="question" placeholder="这篇论文的方法与基线有什么不同？请引用原文。" required maxLength={10000} /></label><button disabled={!providerId || jobs.some(j => j.kind === 'chat' && j.resource_id === conversation && ['queued','running'].includes(j.state))}>发送问题</button></form></section>}
        {tab === 'summary' && <section><h2>个人总结</h2><p>保存在当前工作区，重新登录和更换设备后继续编辑。</p><textarea aria-label="个人总结" rows={12} maxLength={10000} value={summary} onChange={e => setSummary(e.target.value)} /><button onClick={() => void action(async () => { await api(`/papers/${selected.id}/summary`, 'PUT', { content: summary }); setNotice('总结已保存到服务器') })}>保存总结</button></section>}
      </>}
    </main></div></div>
  )
}
