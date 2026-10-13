import { API_BASE } from './urls'
import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from './Markdown'
import { FileText, Plus, MessageSquare, StickyNote, BookOpen, Network, ArrowLeft, Check } from 'lucide-react'
import PdfReader from './PdfReader'
import Neighbors from './Neighbors'
import { PaperTools } from './Knowledge'
import './notebook.css'
type Row = Record<string, any>
export default function NotebookDesk({ target, api, action, jobs, providerId, model, sidebarOpen, onHome, onExternal }: Row) {
  const scope = target.book_id ? 'book' : 'paper', scopeId = target.book_id || target.paper_id
  const [book, setBook] = useState<Row | null>(null), [sources, setSources] = useState<Row[]>([])
  const [checked, setChecked] = useState<string[]>([]), [filter, setFilter] = useState('')
  const [paper, setPaper] = useState<Row | null>(null), [page, setPage] = useState(target.page || 1), [version, setVersion] = useState('')
  const [summary, setSummary] = useState(''), [pane, setPane] = useState('chat')
  const [conversation, setConversation] = useState(''), [messages, setMessages] = useState<Row[]>([])
  const [quote, setQuote] = useState<Row | null>(null), [citation, setCitation] = useState<Row | null>(null)
  const draftKey = `desk-question:${scope}:${scopeId}`
  const [question, setQuestion] = useState(() => localStorage.getItem(draftKey) || '')
  const [notes, setNotes] = useState<Row[]>([]), [noteId, setNoteId] = useState(''), [noteTitle, setNoteTitle] = useState(''), [noteText, setNoteText] = useState('')
  const [notice, setNotice] = useState(''), [busy, setBusy] = useState(false), [report, setReport] = useState<Row | null>(null)
  const [adding, setAdding] = useState(false), [library, setLibrary] = useState<Row[]>([]), [url, setUrl] = useState('')
  const [sourceError, setSourceError] = useState('')
  const [allBooks, setAllBooks] = useState<Row[]>([]), [neighborTag, setNeighborTag] = useState(''), [matrix, setMatrix] = useState(false)
  const generation = useRef(0), initial = useRef(true), activePaper = useRef('')
  const revision = jobs.map((j: Row) => `${j.id}:${j.state}`).join(',')
  const messagePath = scope === 'book' ? `/knowledge-bases/${scopeId}/messages` : conversation ? `/conversations/${conversation}/messages` : ''
  const pending = jobs.find((j: Row) => (scope === 'book' ? j.kind === 'knowledge_chat' && j.resource_id === scopeId : j.kind === 'chat' && j.resource_id === conversation) && ['queued','running'].includes(j.state))
  const lastFailure = jobs.find((j: Row) => (scope === 'book' ? j.kind === 'knowledge_chat' && j.resource_id === scopeId : j.kind === 'chat' && j.resource_id === conversation) && ['failed','needs_attention'].includes(j.state))
  async function loadNotes() { setNotes((await api(`/workspace-notes?scope=${scope}&scope_id=${scopeId}`)).items) }
  async function open(id: string, location?: Row) {
    const request = ++generation.current
    const p = await api(`/papers/${id}`)
    if (request !== generation.current) return
    activePaper.current = id; setPaper(p); setSummary(localStorage.getItem(`notes:${id}`) ?? p.summary)
    localStorage.setItem(`desk-current:${scope}:${scopeId}`, id)
    const v = location?.version_id || location?.document_version_id || p.active_version
    setVersion(v)
    const count = p.versions.find((item: Row) => item.id === v)?.page_count || p.metadata.page_count || 1
    setPage(Math.max(1, Math.min(count, location?.page || location?.page_start || Number(localStorage.getItem(`desk-page:${id}`)) || 1)))
    setCitation(location ? { quote: location.quote || location.exact_quote, nonce: Date.now() } : null)
    setSourceError('')
    const reports = await api(`/papers/${id}/reports`)
    const current = reports.items.find((r: Row) => r.version_id === p.active_version)
    const detail = current ? await api(`/papers/${id}/reports/${current.id}`) : null
    if (request === generation.current) setReport(detail)
  }
  async function loadSources() {
    const b = scope === 'book' ? await api(`/knowledge-bases/${scopeId}`) : null
    const list: Row[] = b ? b.papers : [await api(`/papers/${scopeId}`)]
    setBook(b); setSources(list)
    const firstLoad = initial.current
    let saved: string[] | null = null
    try { const value = JSON.parse(localStorage.getItem(`desk-checked:${scope}:${scopeId}`) || 'null'); if (Array.isArray(value)) saved = value } catch { /* A damaged local preference falls back to all sources. */ }
    setChecked(previous => firstLoad ? (saved ?? list.map((p: Row) => p.id)).filter(id => list.some((p: Row) => p.id === id)) : previous.filter(id => list.some((p: Row) => p.id === id)))
    if (initial.current) {
      initial.current = false
      const preferred = target.paper_id || localStorage.getItem(`desk-current:${scope}:${scopeId}`)
      const chosen = list.find((p: Row) => p.id === preferred) || list[0]
      if (chosen) await open(chosen.id, target.version || target.page ? { version_id: target.version, page: target.page } : undefined)
    } else if (!activePaper.current && list.length) {
      await open(list[0].id)
    }
  }
  useEffect(() => { void action(async () => { await loadSources(); await loadNotes(); setAllBooks((await api('/knowledge-bases')).items); if (scope === 'paper') setConversation((await api(`/papers/${scopeId}/conversations`, 'POST')).id) }) }, [scopeId])
  useEffect(() => { if (messagePath) void action(async () => setMessages((await api(messagePath)).items)); void action(loadSources); void action(loadNotes) }, [revision, messagePath])
  useEffect(() => { if (!paper) return; let dead = false; void action(async () => { const list = await api(`/papers/${paper.id}/reports`); const r = list.items.find((r: Row) => r.version_id === paper.active_version); const value = r ? await api(`/papers/${paper.id}/reports/${r.id}`) : null; if (!dead) setReport(value) }); return () => { dead = true } }, [revision, paper?.id])
  useEffect(() => { localStorage.setItem(draftKey, question) }, [question, draftKey])
  useEffect(() => { if (!initial.current) localStorage.setItem(`desk-checked:${scope}:${scopeId}`, JSON.stringify(checked)) }, [checked, scopeId])
  useEffect(() => { if (paper) localStorage.setItem(`desk-page:${paper.id}`, String(page)) }, [paper?.id, page])
  async function submit(path: string, body?: unknown) {
    const job = await api(path, 'POST', body, crypto.randomUUID())
    setNotice('已开始处理，完成后会显示在这里。')
    return job
  }
  async function locate(ev: Row) { await open(ev.paper_id || paper?.id, ev) }
  function references(evidence: Row = {}) {
    return evidence.sources?.map((ev: Row, i: number) => <button key={i} className="citation-chip" title={ev.quote || ev.exact_quote} onClick={() => void action(() => locate(ev))}>[{ev.id || `S${i + 1}`}] {ev.title ? ev.title.slice(0, 32) : '原文'} · 第 {ev.page || ev.page_start} 页</button>)
  }
  function markdown(content: string, evidence: Row = {}) {
    const refs = evidence.sources || []
    const find = (id: string) => refs.find((r: Row, i: number) => String(r.id || `S${i + 1}`) === id || `S${i + 1}` === id)
    const linked = content.replace(/\[(S?\d+)\]/g, (whole, value) => { const id = value.startsWith('S') ? value : `S${value}`; return find(id) ? `[${value}](#citation-${id})` : whole })
    return <ReactMarkdown math gfm components={{ a: ({href,children}) => {
      const ev = href?.startsWith('#citation-') ? find(href.slice(10)) : null
      return ev ? <button className="inline-citation" title={ev.quote || ev.exact_quote} onClick={() => void action(() => locate(ev))}>{children}</button> : <a href={href} target="_blank" rel="noreferrer">{children}</a>
    } }}>{linked}</ReactMarkdown>
  }
  async function saveAnswer(m: Row) {
    await api('/workspace-notes', 'POST', { scope, scope_id: scopeId, source_message_id: m.id, title: '回答笔记 · ' + new Date().toLocaleDateString() })
    await loadNotes(); setNotice('已保存为笔记，原文引用一并保留。')
  }
  function capture(value: Row) { setQuote({...value,title:paper?.title}); setPane('chat'); setChecked(ids => ids.includes(value.paper_id) ? ids : [...ids, value.paper_id]); window.setTimeout(() => window.document.querySelector<HTMLTextAreaElement>('.desk-composer textarea')?.focus(), 0) }
  async function send() {
    if (!messagePath || busy || pending || !checked.length) return
    setBusy(true)
    const content = quote ? `${question || '请解释这段内容。'}\n\n选中的原文（${String(quote.title || paper?.title).slice(0,160)}，第 ${quote.page} 页）：\n${String(quote.quote).slice(0,1500)}` : question
    try {
      await submit(messagePath, { content, provider_id: providerId, model, ...(scope === 'book' ? { paper_ids: checked } : {}) })
      setQuestion(''); setQuote(null); setMessages((await api(messagePath)).items)
    } finally { setBusy(false) }
  }
  const notebookNotes = <section className="desk-saved-notes"><div className="section-heading"><h2>{scope === 'book' ? '知识库笔记' : '保存的笔记'}</h2><button className="quiet" onClick={() => { setNoteId('new'); setNoteTitle('研究笔记'); setNoteText(localStorage.getItem(`note-draft:${scopeId}`) || '') }}><Plus size={14} /> 新建</button></div>
    {noteId && <form onSubmit={e => { e.preventDefault(); void action(async () => { if (noteId === 'new') await api('/workspace-notes','POST',{ scope, scope_id: scopeId, title: noteTitle, content: noteText }); else await api(`/workspace-notes/${noteId}`,'PUT',{ title: noteTitle, content: noteText }); setNoteId(''); localStorage.removeItem(`note-draft:${scopeId}`); await loadNotes(); setNotice('笔记已保存') }) }}><input aria-label="笔记标题" required value={noteTitle} maxLength={120} onChange={e => setNoteTitle(e.target.value)} /><textarea aria-label="笔记正文" required rows={6} value={noteText} maxLength={30000} onChange={e => { setNoteText(e.target.value); localStorage.setItem(`note-draft:${scopeId}`,e.target.value) }} /><div className="toolbar"><button>保存这条笔记</button><button type="button" className="quiet" onClick={() => setNoteId('')}>取消</button></div></form>}
    {notes.map(n => <details className="saved-note" key={n.id}><summary><StickyNote size={14} /> {n.title}</summary>{markdown(n.content,n.evidence)}<div className="citation-list">{references(n.evidence)}</div><div className="toolbar"><button className="quiet" onClick={() => { setNoteId(n.id); setNoteTitle(n.title); setNoteText(n.content) }}>编辑</button><button className="quiet" onClick={() => { if (window.confirm('删除这条笔记？')) void action(async () => { await api(`/workspace-notes/${n.id}`,'DELETE'); await loadNotes() }) }}>删除</button></div></details>)}
    {!notes.length && <p className="desk-muted">记录自己的理解，或把有用的回答保存到这里。</p>}
  </section>
  const chat = <div className="desk-chat"><div className="chat-history">
    {!messages.length && <div className="chat-welcome"><MessageSquare size={28} /><h2>从一个问题开始</h2><p>{book?.description || paper?.principle || '选择左侧资料，围绕论文的原理、方法或实验继续提问。'}</p><div className="suggested-questions">{['这些资料主要解决什么问题？','解释核心方法，并引用原文。', ...(sources.length > 1 ? ['比较所选论文的共同点与差异。'] : ['实验结果能支持哪些结论？'])].map(q => <button className="quiet" key={q} onClick={() => setQuestion(q)}>{q}</button>)}</div></div>}
    {messages.map(m => <article className={`desk-message ${m.role}`} key={m.id}><b>{m.role === 'user' ? '你' : 'FastRead'}</b>{markdown(m.content,m.evidence)}<div className="citation-list">{references(m.evidence)}</div>{m.role === 'assistant' && <button className="save-answer quiet" onClick={() => void action(() => saveAnswer(m))}>{notes.some(n => n.source_message_id === m.id) ? <><Check size={14} /> 已存入笔记</> : <><StickyNote size={14} /> 保存为笔记</>}</button>}</article>)}
    {(busy || pending) && <p className="answer-progress" role="status">正在结合所选资料回答…</p>}
    {lastFailure && !pending && <details className="answer-failure"><summary>有一条回答未完成</summary><p>{lastFailure.error || '请稍后重试。'}</p><button className="quiet" onClick={() => { const last = [...messages].reverse().find(m => m.role === 'user'); if(last) setQuestion(last.content) }}>恢复问题</button></details>}
    </div><form className="desk-composer" onSubmit={e => { e.preventDefault(); void action(send) }}>
    {quote && <blockquote><span>选文 · 第 {quote.page} 页</span><p>{quote.quote}</p><button type="button" className="quiet" onClick={() => setQuote(null)}>移除选文</button></blockquote>}
    <textarea aria-label="向所选资料提问" value={question} onChange={e => setQuestion(e.target.value)} placeholder={checked.length ? '输入问题，或在 PDF 上选中一段文字…' : '请先勾选左侧资料'} maxLength={quote ? 3000 : 5000} rows={3} /><div className="composer-footer"><span>参考 {checked.length} 篇资料</span><button disabled={!providerId || !checked.length || busy || !!pending || (!question.trim() && !quote)}>发送</button></div></form></div>
  const reportPanel = <section className="desk-report">{paper && <details><summary>标签、原理与知识库归属</summary><PaperTools paper={paper} books={allBooks} api={api} action={action} openPaper={onExternal} submitJob={submit} providerId={providerId} model={model} revision={revision} onTag={tag => { setNeighborTag(tag); setPane('neighbors') }} reload={async () => { await loadSources(); setPaper(await api(`/papers/${paper.id}`)) }} /></details>}<h2>阅读报告</h2><p className="desk-muted">{paper?.title}</p><button disabled={!paper || !providerId || jobs.some((j: Row) => j.kind === 'report' && j.resource_id === paper?.id && ['queued','running'].includes(j.state))} onClick={() => void action(() => submit(`/papers/${paper?.id}/reports`,{provider_id:providerId,model}))}>{report ? '重新生成报告' : '生成阅读报告'}</button>{report && <>{['key_questions','process','contributions'].map(k => <div key={k}><h3>{{key_questions:'关键问题',process:'方法过程',contributions:'主要贡献'}[k]}</h3>{report.content[k]?.map((r: Row,i:number) => <article key={i}><b>{r.question || r.step || r.title}</b><ReactMarkdown>{r.answer || r.description || ''}</ReactMarkdown>{r.evidence?.map((ev:Row,j:number) => <button key={j} className="citation-chip" title={ev.exact_quote} onClick={() => void action(() => locate({...ev,version_id:report.version_id}))}>第 {ev.page_start || ev.page} 页 · 查看依据</button>)}</article>)}</div>)}<a href={`${API_BASE}/papers/${paper?.id}/export`} download>导出报告</a></>}</section>
  const paneHeader = <nav className="desk-pane-tabs" aria-label="研究工具">{[['chat','对话',MessageSquare],['notes','笔记',StickyNote],['report','报告',BookOpen],['neighbors','近邻',Network]].map(([id,label,Icon]) => { const I=Icon as typeof FileText;return <button key={String(id)} className={pane === id ? 'active' : ''} onClick={() => setPane(String(id))}><I size={16} />{String(label)}</button> })}</nav>
  const companion = pane === 'chat' ? chat : pane === 'report' ? reportPanel : paper ? <Neighbors key={paper.id + neighborTag} initialTag={neighborTag} paper={paper} api={api} action={action} openPaper={onExternal} submitJob={submit} revision={revision} pending={jobs.some((j:Row) => j.kind === 'neighbors' && j.resource_id === paper.id && ['queued','running'].includes(j.state))} /> : null
  return <section className={`notebook-desk ${sidebarOpen ? '' : 'sources-closed'}`}>
    <aside id="desk-sources" className="desk-sources"><button className="back-home quiet" onClick={onHome}><ArrowLeft size={15} /> 所有知识库</button><h1>{book?.name || '论文阅读'}</h1><div className="section-heading"><h2>资料</h2><button className="quiet" onClick={() => void action(async () => { setAdding(true); setLibrary((await api('/papers?limit=100')).items) })}><Plus size={16} /> 添加</button></div><input aria-label="筛选知识库资料" placeholder="筛选资料…" value={filter} onChange={e => setFilter(e.target.value)} /><label className="select-sources"><input type="checkbox" checked={!!sources.length && checked.length === sources.length} onChange={e => setChecked(e.target.checked ? sources.map(p => p.id) : [])} />选择全部 <span>{checked.length} / {sources.length}</span></label>
    <nav>{sources.filter(p => p.title.toLowerCase().includes(filter.toLowerCase())).map(p => <div className={`desk-source ${paper?.id === p.id ? 'active' : ''}`} key={p.id}><input type="checkbox" aria-label={`问答参考 ${p.title}`} checked={checked.includes(p.id)} onChange={e => setChecked(ids => e.target.checked ? [...ids,p.id] : ids.filter(id => id !== p.id))} /><button onClick={() => void action(() => open(p.id))}><FileText size={16} /><span>{p.title}</span></button></div>)}</nav><p className="desk-muted">勾选决定问答参考范围；点击标题阅读原文。</p><button className="quiet" onClick={() => setMatrix(true)}>查看关系矩阵</button>
    </aside><div className="desk-reading"><div className="desk-reading-heading"><div><span>{book ? book.name : '论文阅读'}</span><h2>{paper?.title || '添加资料，开始阅读'}</h2></div>{paper && <details><summary>文档版本</summary><select aria-label="文档版本" value={version} onChange={e => { setVersion(e.target.value); setPage(1); setCitation(null) }}>{paper.versions.map((v:Row) => <option key={v.id} value={v.id}>{new Date(v.created*1000).toLocaleDateString()}{v.id === paper.active_version ? '（当前）' : ''}</option>)}</select></details>}</div>
    {paper ? <PdfReader key={paper.id} paper={paper} version={version} page={page} setPage={setPage} api={api} summary={summary} setSummary={setSummary} onSaved={s => setPaper(p => p ? {...p,summary:s} : p)} pane={pane} onPane={setPane} onQuote={capture} citation={citation} companion={companion} companionHeader={paneHeader} notebookNotes={notebookNotes} /> : <div className="desk-empty"><FileText size={40} /><h2>把论文放进来</h2><p>{book?.description || '上传 PDF 或从资料库添加论文，就可以阅读和提问。'}</p><button onClick={() => void action(async () => { setAdding(true); setLibrary((await api('/papers?limit=100')).items) })}>添加资料</button></div>}
    {notice && <div className="desk-toast" role="status">{notice}<button className="quiet" onClick={() => setNotice('')}>关闭</button></div>}{sourceError && <p role="alert">{sourceError}</p>}
    </div>
    {matrix && <div className="desk-modal-backdrop" onClick={() => setMatrix(false)}><section className="desk-modal matrix-modal" role="dialog" aria-modal="true" aria-label="关系矩阵" onClick={e => e.stopPropagation()}><div className="section-heading"><h2>论文与标签</h2><button className="quiet" onClick={() => setMatrix(false)}>关闭</button></div><p className="desk-muted">点击标签，选择同标签的论文参与问答。</p><div className="matrix-scroll"><table className="relation-matrix"><thead><tr><th>论文</th>{[...new Set<string>(sources.flatMap(p => p.tags || []))].map(t => <th key={t}><button className="tag" onClick={() => { setChecked(sources.filter(p => p.tags?.includes(t)).map(p => p.id)); setMatrix(false); setPane('chat') }}>{t}</button></th>)}</tr></thead><tbody>{sources.map(p => <tr key={p.id}><th><button className="quiet" onClick={() => { void action(() => open(p.id)); setMatrix(false) }}>{p.title}</button></th>{[...new Set<string>(sources.flatMap(p => p.tags || []))].map(t => <td key={t}>{p.tags?.includes(t) ? '●' : '—'}</td>)}</tr>)}</tbody></table></div></section></div>}
    {adding && <div className="desk-modal-backdrop" onClick={() => setAdding(false)}><section className="desk-modal" role="dialog" aria-modal="true" aria-label="添加资料" onClick={e => e.stopPropagation()}><div className="section-heading"><h2>添加资料</h2><button className="quiet" onClick={() => setAdding(false)}>关闭</button></div><form onSubmit={e => { e.preventDefault(); void action(async () => { await submit('/imports/url',{url,knowledge_id:target.book_id || ''}); setUrl(''); setAdding(false) }) }}><label>论文链接<input value={url} onChange={e => setUrl(e.target.value)} type="url" required placeholder="https://arxiv.org/pdf/…" /></label><button>导入链接</button></form><label className="file-button">上传 PDF<input aria-label="上传资料 PDF" type="file" accept="application/pdf" onChange={e => { const file=e.target.files?.[0];if(file) void action(async () => { const data=new FormData();data.set('file',file);data.set('knowledge_id',target.book_id || '');await submit('/imports/pdf',data);setAdding(false) }) }} /></label>{scope === 'book' && <><h3>从资料库添加</h3>{library.filter(p => !sources.some(s => s.id === p.id)).map(p => <button className="add-existing quiet" key={p.id} onClick={() => void action(async () => { await api(`/knowledge-bases/${scopeId}/papers`,'POST',{paper_ids:[p.id]});await loadSources();setChecked(ids => [...new Set([...ids,p.id])]);if(!paper) await open(p.id);setAdding(false) })}><Plus size={15} />{p.title}</button>)}</>}</section></div>}
  </section>
}
