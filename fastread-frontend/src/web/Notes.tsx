import { useEffect, useState } from 'react'
import { ArrowUpRight, Check, Plus, Search, StickyNote } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api, type Row } from './api'
import type { WorkspaceRoute } from './navigation'

export default function Notes({
  books,
  navigate,
  revision,
}: {
  books: Row[]
  navigate: (r: WorkspaceRoute) => void
  revision: string
}) {
  const [scope, setScope] = useState('')
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [papers, setPapers] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [notes, setNotes] = useState<Row[]>([])
  const [paper, setPaper] = useState<Row | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState<Row | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    let active = true
    api(`/papers?limit=100&q=${encodeURIComponent(search)}`)
      .then(data => {
        if (active) {
          setPapers(data.items)
          setTotal(data.total)
        }
      })
      .catch(e => {
        if (active) setError(e.message)
      })
    return () => {
      active = false
    }
  }, [search, revision])
  useEffect(() => {
    if (!scope) return
    let active = true
    const [type, id] = scope.split(':')
    setLoading(true)
    setError('')
    Promise.all([
      api(`/workspace-notes?scope=${type}&scope_id=${encodeURIComponent(id)}`),
      type === 'paper' ? api(`/papers/${id}`) : Promise.resolve(null),
    ])
      .then(([data, detail]) => {
        if (active) {
          setNotes(data.items)
          setPaper(detail)
        }
      })
      .catch(e => {
        if (active) setError(e.message)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [scope, revision, refresh])
  function edit(note: Row) {
    const key = `product-note:${scope}:${note.id}`
    let draft
    try {
      draft = JSON.parse(localStorage.getItem(key) || 'null')
    } catch {
      /* Ignore damaged local draft. */
    }
    setEditing({ ...note, ...draft })
    setSaved(false)
  }
  function change(value: Row) {
    setEditing(value)
    setSaved(false)
    localStorage.setItem(
      `product-note:${scope}:${value.id}`,
      JSON.stringify({ title: value.title, content: value.content })
    )
  }
  async function save() {
    if (!editing) return
    setSaving(true)
    setError('')
    try {
      const [type, id] = scope.split(':')
      if (editing.id === 'new')
        await api('/workspace-notes', 'POST', {
          scope: type,
          scope_id: id,
          title: editing.title,
          content: editing.content,
        })
      else
        await api(`/workspace-notes/${editing.id}`, 'PUT', {
          title: editing.title,
          content: editing.content,
        })
      localStorage.removeItem(`product-note:${scope}:${editing.id}`)
      setEditing(null)
      setSaved(true)
      setRefresh(n => n + 1)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }
  const [type, id] = scope.split(':')
  const openSource = () =>
    navigate(type === 'book' ? { view: 'books', book: id } : { view: 'library', paper: id })
  return (
    <section className="library-page notes-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">保留自己的理解</div>
          <h1>笔记</h1>
          <p>按论文或知识库查看，保存的回答仍保留原文引用。</p>
        </div>
        {scope && (
          <button onClick={() => edit({ id: 'new', title: '', content: '' })}>
            <Plus size={16} />
            新建笔记
          </button>
        )}
      </div>
      <div className="notes-source-tools">
        <form
          className="library-search"
          onSubmit={e => {
            e.preventDefault()
            setSearch(query.trim())
          }}
        >
          <Search size={16} />
          <input
            aria-label="查找笔记所属论文"
            placeholder="按论文标题查找…"
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <button className="quiet">查找</button>
        </form>
        <select
          aria-label="笔记所属资料"
          value={scope}
          onChange={e => {
            setScope(e.target.value)
            setEditing(null)
            setSaved(false)
          }}
        >
          <option value="">选择知识库或论文</option>
          <optgroup label="知识库">
            {books.map(b => (
              <option key={b.id} value={`book:${b.id}`}>
                {b.name}
              </option>
            ))}
          </optgroup>
          <optgroup label="论文">
            {papers.map(p => (
              <option key={p.id} value={`paper:${p.id}`}>
                {p.title}
              </option>
            ))}
          </optgroup>
        </select>
      </div>
      {total > 100 && <p className="muted">列出最近加入的 100 篇论文，可按标题查找更早的资料。</p>}
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      {saved && (
        <p className="save-state" role="status">
          <Check size={14} /> 已保存到资料库
        </p>
      )}
      {!scope ? (
        <div className="product-empty">
          <StickyNote size={32} />
          <h2>从一份资料找回你的想法</h2>
          <p>选择知识库或论文，查看对应笔记与原文。</p>
        </div>
      ) : loading ? (
        <p role="status">正在读取笔记…</p>
      ) : (
        <>
          <div className="list-caption">
            <span>{notes.length} 条保存的笔记</span>
            <button className="quiet" onClick={openSource}>
              打开阅读工作台
              <ArrowUpRight size={14} />
            </button>
          </div>
          {editing && (
            <form
              className="note-editor"
              onSubmit={e => {
                e.preventDefault()
                void save()
              }}
            >
              <input
                aria-label="笔记标题"
                placeholder="笔记标题"
                required
                maxLength={120}
                value={editing.title}
                onChange={e => change({ ...editing, title: e.target.value })}
              />
              <textarea
                aria-label="笔记正文"
                placeholder="写下你的理解…"
                required
                maxLength={30000}
                rows={10}
                value={editing.content}
                onChange={e => change({ ...editing, content: e.target.value })}
              />
              <div>
                <small>编辑草稿暂存在本机，点击保存后写入资料库。</small>
                <button
                  type="button"
                  className="quiet"
                  disabled={saving}
                  onClick={() => setEditing(null)}
                >
                  收起
                </button>
                <button disabled={saving}>{saving ? '保存中…' : '保存笔记'}</button>
              </div>
            </form>
          )}
          <div className="saved-notes-list">
            {notes.map(n => (
              <article key={n.id}>
                <div>
                  <span className="note-origin">
                    {n.source_message_id ? '保存的回答' : '个人笔记'}
                  </span>
                  <small>{new Date(n.updated * 1000).toLocaleDateString('zh-CN')}</small>
                </div>
                <h2>{n.title}</h2>
                <ReactMarkdown>{n.content}</ReactMarkdown>
                {n.evidence?.sources?.map((s: Row, i: number) => (
                  <button
                    className="citation-chip"
                    key={i}
                    onClick={() =>
                      navigate({
                        view: 'library',
                        paper: s.paper_id || (type === 'paper' ? id : undefined),
                        page: s.page || s.page_start,
                        version: s.version_id || s.document_version_id,
                      })
                    }
                  >
                    [{s.id || i + 1}] {s.title || '原文'} · 第 {s.page || s.page_start} 页
                  </button>
                ))}
                <button className="quiet note-edit-button" onClick={() => edit(n)}>
                  编辑笔记
                </button>
              </article>
            ))}
          </div>
          {paper?.summary && (
            <article className="summary-note">
              <span className="note-origin">论文阅读总结</span>
              <ReactMarkdown>{paper.summary}</ReactMarkdown>
              <button className="quiet" onClick={openSource}>
                回到原文编辑
                <ArrowUpRight size={14} />
              </button>
            </article>
          )}
          {!notes.length && !editing && (
            <div className="product-empty">
              <StickyNote size={28} />
              <h2>这里还没有保存的笔记</h2>
              <p>可以新建一条，或在阅读时把有用的回答保存过来。页内批注在阅读工作台中查看。</p>
              <button className="quiet" onClick={() => edit({ id: 'new', title: '', content: '' })}>
                <Plus size={15} />
                写第一条笔记
              </button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
