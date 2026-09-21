import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { OrganizeButton } from './Organize'

type Row = Record<string, any>
type Props = {
  api: (path: string, method?: string, body?: unknown, key?: string) => Promise<any>
  action: (fn: () => Promise<unknown>) => Promise<unknown>
  openPaper: (id: string, page?: number, version?: string) => Promise<void>
  submitJob: (path: string, body?: unknown) => Promise<void>
  providerId: string
  model: string
  revision: string
}

export function PaperTools({ paper, books, api, action, providerId, model, onTag, reload }: Props & { paper: Row; books: Row[]; onTag: (tag: string) => void; reload: () => Promise<void> }) {
  const [tags, setTags] = useState<string>((paper.tags || []).join(', '))
  const [bookId, setBookId] = useState('')
  useEffect(() => setTags((paper.tags || []).join(', ')), [paper.id, JSON.stringify(paper.tags)])
  return <section className="paper-tools">
    <div className="tag-row">{(paper.tags || []).map((tag: string) => <button className="tag" key={tag} onClick={() => onTag(tag)}># {tag}</button>)}</div>
    {paper.principle && <div className="principle"><b>核心原理</b><p>{paper.principle}</p></div>}
    <div className="toolbar"><label>归入知识库<select aria-label="归入知识库" value={bookId} onChange={e => setBookId(e.target.value)}><option value="">让 AI 自动判断</option>{books.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
      <OrganizeButton ids={[paper.id]} disabled={!providerId} body={{ provider_id: providerId, model, knowledge_id: bookId }} label="智能整理原理与标签" />
      {bookId && <button className="quiet" onClick={() => void action(async () => { await api(`/knowledge-bases/${bookId}/papers`, 'POST', { paper_ids: [paper.id] }); await reload() })}>直接加入</button>}
    </div>
    <details><summary>编辑标签与知识库归属</summary><form className="inline-form" onSubmit={e => { e.preventDefault(); void action(async () => { await api(`/papers/${paper.id}/tags`, 'PUT', { tags: tags.split(/[,，]/).map(t => t.trim()).filter(Boolean) }); await reload() }) }}><label>多个标签，用逗号分隔<input aria-label="论文标签" value={tags} onChange={e => setTags(e.target.value)} maxLength={800} /></label><button>保存标签</button></form>
      <div className="tag-row">{(paper.knowledge_bases || []).map((b: Row) => <button className="quiet" key={b.id} onClick={() => void action(async () => { await api(`/knowledge-bases/${b.id}/papers/${paper.id}`, 'DELETE'); await reload() })}>{b.name} · 移出</button>)}</div>
    </details>
  </section>
}

export default function Knowledge(props: Props & { initialTag?: string; onOpenBook?: (id: string) => void }) {
  const { api, action, openPaper, submitJob, providerId, model, revision } = props
  const [books, setBooks] = useState<Row[]>([])
  const [bookId, setBookId] = useState('')
  const [book, setBook] = useState<Row | null>(null)
  const [papers, setPapers] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [tag, setTag] = useState(props.initialTag || '')
  const [tags, setTags] = useState<Row[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [target, setTarget] = useState('')
  const [messages, setMessages] = useState<Row[]>([])
  const [matrix, setMatrix] = useState(false)
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [creating, setCreating] = useState(false)
  useEffect(() => { setTag(props.initialTag || ''); setBookId(''); setOffset(0) }, [props.initialTag])
  const requestNumber = useRef(0)
  async function reload() {
    const request = ++requestNumber.current
    const [libraries, allTags] = await Promise.all([api('/knowledge-bases'), api('/tags')])
    if (request !== requestNumber.current) return
    setBooks(libraries.items); setTags(allTags.items)
    if (bookId) {
      const [detail, history] = await Promise.all([api(`/knowledge-bases/${bookId}`), api(`/knowledge-bases/${bookId}/messages`)])
      if (request !== requestNumber.current) return
      setBook(detail); setPapers(detail.papers); setTotal(detail.papers.length); setMessages(history.items)
    } else {
      const result = await api(`/papers?limit=20&offset=${offset}&tag=${encodeURIComponent(tag)}`)
      if (request !== requestNumber.current) return
      setBook(null); setPapers(result.items); setTotal(result.total)
    }
  }
  useEffect(() => { void action(reload) }, [bookId, offset, tag, revision])
  useEffect(() => { setSelected([]); setQuestion('') }, [bookId, tag, offset])
  function chooseTag(value: string) { setTag(value); setBookId(''); setOffset(0) }
  async function ask() {
    setBusy(true)
    try { await submitJob(`/knowledge-bases/${bookId}/messages`, { content: question, provider_id: providerId, model }); setQuestion(''); await reload() }
    finally { setBusy(false) }
  }
  const columns = [...new Set(papers.flatMap(p => p.tags || []))].slice(0, 16) as string[]
  return <section className="knowledge-home">
    <div className="knowledge-hero"><div><div className="eyebrow">论文与知识库</div><h1>阅读论文，整理知识库</h1><p>阅读原文、记录想法，按主题查找相关论文。</p></div><button onClick={() => setCreating(!creating)}>＋ 新建知识库</button></div>
    {creating && <form className="create-book" onSubmit={e => { e.preventDefault(); const f = e.currentTarget; void action(async () => { const result = await api('/knowledge-bases', 'POST', Object.fromEntries(new FormData(f))); setBookId(result.id); props.onOpenBook?.(result.id); setCreating(false); f.reset() }) }}><label>名称<input name="name" placeholder="例如：大模型推理与检索" maxLength={80} required /></label><label>关注的问题<input name="description" placeholder="可不填，AI 会自动生成关注的问题" maxLength={1000} /></label><button>创建知识库</button></form>}
    <nav className="book-grid" aria-label="知识库目录"><button className={!bookId && !tag ? 'book-card active' : 'book-card'} onClick={() => { setBookId(''); setTag(''); setOffset(0) }}><span>资料库</span><strong>全部论文</strong><small>阅读、收藏与归类</small></button>{books.map(b => <button key={b.id} className={bookId === b.id ? 'book-card active' : 'book-card'} onClick={() => { if(props.onOpenBook) props.onOpenBook(b.id); else { setBookId(b.id); setTag(''); setOffset(0) } }}><span>知识库 · {b.paper_count} 篇</span><strong>{b.name}</strong><small>{b.description || (['queued', 'running'].includes(b.questions_status) ? 'AI 正在生成关注的问题…' : '关注的问题尚未生成')}</small></button>)}</nav>
    <div className="section-heading"><div><h2>{book?.name || (tag ? `标签：${tag}` : '我的论文')}</h2><p>{book?.description || `${total} 篇论文 · 点击标签查看相关工作`}</p></div><button className="quiet" onClick={() => setMatrix(!matrix)}>{matrix ? '卡片视图' : '关系矩阵'}</button></div>
    {book && !book.description && <p><button className="quiet" disabled={['queued', 'running'].includes(books.find(b => b.id === bookId)?.questions_status)} onClick={() => void action(async () => { await api(`/knowledge-bases/${bookId}/questions`, 'POST'); await reload() })}>{['queued', 'running'].includes(books.find(b => b.id === bookId)?.questions_status) ? 'AI 正在生成关注的问题…' : '生成关注的问题'}</button></p>}
    {!!tags.length && <div className="tag-row"><button className="tag" onClick={() => chooseTag('')}>全部标签</button>{tags.slice(0, 30).map(t => <button key={t.tag} className={tag === t.tag ? 'tag active' : 'tag'} onClick={() => chooseTag(t.tag)}># {t.tag} <small>{t.paper_count}</small></button>)}</div>}
    <div className="selection-bar"><span>已选 {selected.length} 篇</span><select aria-label="所选论文加入知识库" value={target} onChange={e => setTarget(e.target.value)}><option value="">选择知识库</option>{books.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select><button className="quiet" disabled={!selected.length || !target} onClick={() => void action(async () => { await api(`/knowledge-bases/${target}/papers`, 'POST', { paper_ids: selected }); setSelected([]); await reload() })}>加入知识库</button><OrganizeButton ids={selected} disabled={!providerId || selected.some(id => !papers.find(p => p.id === id)?.active_version)} body={{ provider_id: providerId, model, knowledge_id: target }} label="AI 整理所选论文" /></div>
    {matrix ? <div className="matrix-scroll"><p className="muted">论文 × 研究标签。圆点表示共享标签，不代表因果关系。</p><table className="relation-matrix"><thead><tr><th>论文</th>{columns.map(t => <th key={t}><button className="tag" onClick={() => chooseTag(t)}>{t}</button></th>)}</tr></thead><tbody>{papers.map(p => <tr key={p.id}><th><button className="quiet" onClick={() => void action(() => openPaper(p.id))}>{p.title}</button></th>{columns.map(t => <td key={t}>{p.tags?.includes(t) ? <span aria-label="包含此标签">●</span> : '—'}</td>)}</tr>)}</tbody></table>{!columns.length && <p>先智能整理或手动添加标签，即可查看关系矩阵。</p>}</div> : <div className="knowledge-papers">{papers.map(p => <article key={p.id} className="knowledge-paper"><div className="card-top"><label className="selection-label"><input type="checkbox" aria-label={`选择论文 ${p.title}`} checked={selected.includes(p.id)} onChange={e => setSelected(current => e.target.checked ? [...current, p.id] : current.filter(id => id !== p.id))} />选择</label><small>{p.metadata?.year || p.year || '年份待核实'} · {p.metadata?.page_count || p.page_count || '?'} 页</small></div><h3><button className="paper-title" onClick={() => void action(() => openPaper(p.id))}>{p.title}</button></h3><div className="principle"><b>核心原理</b><p>{p.principle || '尚未整理。点击 AI 整理，从论文原文生成简短原理和多个标签。'}</p></div><div className="tag-row">{p.tags?.map((t: string) => <button key={t} className="tag" onClick={() => chooseTag(t)}># {t}</button>)}</div><div className="toolbar"><button className="quiet" onClick={() => void action(() => openPaper(p.id))}>阅读全文 →</button><OrganizeButton ids={[p.id]} disabled={!providerId || !p.active_version} body={{ provider_id: providerId, model, knowledge_id: bookId }} />{bookId && <button className="quiet" onClick={() => void action(async () => { await api(`/knowledge-bases/${bookId}/papers/${p.id}`, 'DELETE'); await reload() })}>移出</button>}</div>{!!p.principle_evidence?.length && <details><summary>原理的原文依据</summary>{p.principle_evidence.map((s: Row, i: number) => <blockquote key={i}><button className="page-link" onClick={() => void action(() => openPaper(s.paper_id, s.page, s.version_id))}>第 {s.page} 页</button> {s.quote}</blockquote>)}</details>}</article>)}</div>}
    {!papers.length && <div className="knowledge-empty"><h3>{book ? '把论文放进来，开始建立联系' : '从第一篇论文开始'}</h3><p>{book ? '在“全部论文”勾选论文，加入这个知识库；也可导入时选择它。' : '在左侧上传 PDF 或导入链接。未指定知识库时，AI 会自动归类。'}</p></div>}
    {!bookId && total > 20 && <div className="pagination"><button disabled={!offset} onClick={() => setOffset(Math.max(0,offset-20))}>上一页</button><span>{offset+1}–{Math.min(total,offset+20)} / {total}</span><button disabled={offset+20>=total} onClick={() => setOffset(offset+20)}>下一页</button></div>}
    {book && <section className="knowledge-chat"><div className="section-heading"><div><h2>向知识库追问</h2><p>比较原理、方法与结论，回答附论文页码。</p></div></div><div className="messages">{messages.map(m => <article className={`message ${m.role}`} key={m.id}><b>{m.role === 'user' ? '你' : 'FastRead'}</b><ReactMarkdown>{m.content}</ReactMarkdown>{m.evidence?.sources?.map((s: Row, i: number) => <blockquote key={i}><button className="page-link" onClick={() => void action(() => openPaper(s.paper_id,s.page,s.version_id))}>[{s.id}] {s.title} · 第 {s.page} 页</button><p>{s.quote}</p></blockquote>)}</article>)}</div><form onSubmit={e => { e.preventDefault(); void action(ask) }}><label>你的问题<textarea aria-label="向知识库追问" value={question} onChange={e => setQuestion(e.target.value)} placeholder="这些论文分别用什么机制解决问题？共同点和差异是什么？" maxLength={5000} required /></label><button disabled={!providerId || !papers.length || busy}>{busy ? '提交中…' : '发送问题'}</button></form></section>}
  </section>
}
