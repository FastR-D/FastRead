import { useEffect, useRef, useState } from 'react'
import {
  Archive,
  ArrowDownToLine,
  ArrowRight,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  FileText,
  FolderPlus,
  LibraryBig,
  Plus,
  Search,
  X,
} from 'lucide-react'
import { api, type Row } from './api'
import { OrganizeButton } from './Organize'
import type { WorkspaceRoute } from './navigation'

export default function Library({
  route,
  navigate,
  books,
  revision,
  providerId,
  model,
  onImport,
  onCreateBook,
  onChanged,
  notify,
  recent,
}: {
  route: WorkspaceRoute
  navigate: (r: WorkspaceRoute) => void
  books: Row[]
  revision: string
  providerId: string
  model: string
  onImport: (paperId?: string) => void
  onCreateBook: () => void
  onChanged: () => void
  notify: (message: string) => void
  recent: Row | null
}) {
  const [papers, setPapers] = useState<Row[]>([])
  const [tags, setTags] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const [selected, setSelected] = useState<string[]>([])
  const [target, setTarget] = useState('')
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState(route.q || '')
  const selectAll = useRef<HTMLInputElement>(null)
  const archived = route.view === 'archive'
  const isBooks = route.view === 'books'
  const offset = route.offset || 0
  useEffect(() => {
    setQuery(route.q || '')
  }, [route.q])
  useEffect(() => {
    if (isBooks) return
    let active = true
    setLoading(true)
    setError('')
    const params = new URLSearchParams({
      limit: '20',
      offset: String(offset),
      archived: String(archived),
      q: route.q || '',
      tag: route.tag || '',
    })
    api(`/papers?${params}`)
      .then(data => {
        if (active) {
          setPapers(data.items)
          setTotal(data.total)
          setSelected(ids => ids.filter(id => data.items.some((p: Row) => p.id === id)))
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
  }, [offset, archived, route.q, route.tag, revision, retry, isBooks])
  useEffect(() => {
    let active = true
    api('/tags')
      .then(data => {
        if (active) setTags(data.items)
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [revision])
  useEffect(() => {
    if (selectAll.current)
      selectAll.current.indeterminate = selected.length > 0 && selected.length < papers.length
  }, [selected, papers])
  async function mutate(fn: () => Promise<void>) {
    setBusy(true)
    setError('')
    try {
      await fn()
      setSelected([])
      setRetry(n => n + 1)
      onChanged()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const openPaper = (paper: Row) =>
    paper.active_version ? navigate({ view: 'library', paper: paper.id }) : onImport(paper.id)

  return (
    <section className="library-page">
      <div className="page-heading">
        <div>
          <div className="page-kicker">你的研究空间</div>
          <h1>{isBooks ? '知识库' : archived ? '已归档' : '文献库'}</h1>
          <p>
            {isBooks
              ? '把相关论文放在一起，围绕同一个问题深入阅读。'
              : archived
                ? '归档的论文与笔记仍然保留，可随时恢复。'
                : '找到值得读的论文，把读过的内容留下来。'}
          </p>
        </div>
        <button className="primary" onClick={isBooks ? onCreateBook : () => onImport()}>
          <Plus size={16} />
          {isBooks ? '新建知识库' : '导入论文'}
        </button>
      </div>
      {isBooks ? (
        <>
          <div className="list-caption">
            <span>{books.length} 个知识库</span>
            <span>按研究问题组织</span>
          </div>
          <div className="collection-grid">
            {books.map((book, i) => (
              <button
                className="collection-card"
                key={book.id}
                onClick={() => navigate({ view: 'books', book: book.id })}
              >
                <span className={`collection-symbol color-${i % 3}`}>
                  <LibraryBig size={22} />
                </span>
                <h2>{book.name}</h2>
                <p>{book.description || '还没有添加研究问题'}</p>
                <div>
                  <span>{book.paper_count} 篇论文</span>
                  <ArrowRight size={16} />
                </div>
              </button>
            ))}
            <button className="collection-card collection-new" onClick={onCreateBook}>
              <FolderPlus size={24} />
              <strong>新建知识库</strong>
              <span>为下一个研究问题留个位置</span>
            </button>
          </div>
        </>
      ) : (
        <>
          {!archived && !route.q && !route.tag && !offset && recent?.active_version && (
            <button className="continue-reading" onClick={() => openPaper(recent)}>
              <span className="continue-icon">
                <BookOpen size={22} />
              </span>
              <span>
                <small>继续上次阅读</small>
                <strong>{recent.title}</strong>
                <span>
                  {recent.page_count || recent.metadata?.page_count || '—'} 页 ·
                  保留阅读位置与本机草稿
                </span>
              </span>
              <ArrowRight size={19} />
            </button>
          )}
          <div className="library-toolbar">
            <form
              className="library-search"
              onSubmit={e => {
                e.preventDefault()
                navigate({ ...route, q: query.trim(), offset: 0 })
              }}
            >
              <Search size={17} />
              <input
                aria-label="搜索文献库"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="搜索论文标题…"
                maxLength={300}
              />
              <button type="submit" className="quiet">
                搜索
              </button>
            </form>
            <select
              aria-label="按标签筛选"
              value={route.tag || ''}
              onChange={e => navigate({ ...route, tag: e.target.value, offset: 0 })}
            >
              <option value="">全部标签</option>
              {tags.map(t => (
                <option key={t.tag} value={t.tag}>
                  {t.tag} · {t.paper_count}
                </option>
              ))}
            </select>
            <span className="sort-label">最近加入</span>
          </div>
          {(route.q || route.tag) && (
            <div className="filter-summary">
              <span>
                {route.q && `标题包含「${route.q}」`}
                {route.q && route.tag && ' · '}
                {route.tag && `标签：${route.tag}`}
              </span>
              <button className="quiet" onClick={() => navigate({ view: route.view })}>
                <X size={13} /> 清除筛选
              </button>
            </div>
          )}
          {!!selected.length && (
            <div className="bulk-toolbar" aria-label="批量操作">
              <span>{selected.length} 篇已选</span>
              {!archived && (
                <>
                  <select
                    aria-label="加入知识库"
                    value={target}
                    onChange={e => setTarget(e.target.value)}
                  >
                    <option value="">选择知识库</option>
                    {books.map(b => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                  <button
                    className="quiet"
                    disabled={!target || busy}
                    onClick={() =>
                      void mutate(async () => {
                        await api(`/knowledge-bases/${target}/papers`, 'POST', {
                          paper_ids: selected,
                        })
                        notify('已加入知识库')
                      })
                    }
                  >
                    加入
                  </button>
                  <OrganizeButton
                    ids={selected}
                    disabled={
                      !providerId ||
                      selected.some(id => !papers.find(p => p.id === id)?.active_version)
                    }
                    body={{ provider_id: providerId, model }}
                    label="整理标签"
                  />
                </>
              )}
              <button className="quiet" onClick={() => setSelected([])} aria-label="取消选择">
                <X size={15} />
              </button>
            </div>
          )}
          {error && (
            <div className="inline-error" role="alert">
              <span>{error}</span>
              <button className="quiet" onClick={() => setRetry(n => n + 1)}>
                重试
              </button>
            </div>
          )}
          {loading ? (
            <div className="library-skeleton" role="status" aria-label="正在加载文献">
              {[0, 1, 2, 3, 4].map(i => (
                <div key={i}>
                  <span />
                  <span />
                </div>
              ))}
            </div>
          ) : !error && !papers.length ? (
            <div className="product-empty">
              <FileText size={32} />
              <h2>
                {route.q || route.tag
                  ? '没有找到匹配的论文'
                  : archived
                    ? '还没有归档的论文'
                    : '从一篇论文开始'}
              </h2>
              <p>
                {route.q || route.tag
                  ? '试试其他标题关键词，或清除筛选。'
                  : archived
                    ? '在论文列表中归档后，可以在这里找回。'
                    : '上传 PDF 或粘贴论文链接，原文和笔记会保存在资料库。'}
              </p>
              {!archived && !route.q && !route.tag && (
                <button onClick={() => onImport()}>
                  <Plus size={16} /> 导入第一篇论文
                </button>
              )}
            </div>
          ) : (
            !error && (
              <div className="paper-table" aria-busy={busy}>
                <div className="paper-table-head">
                  <input
                    ref={selectAll}
                    type="checkbox"
                    aria-label="选择本页全部论文"
                    checked={!!papers.length && selected.length === papers.length}
                    onChange={e => setSelected(e.target.checked ? papers.map(p => p.id) : [])}
                  />
                  <span>论文 / 作者</span>
                  <span>标签</span>
                  <span>原文</span>
                  <span className="sr-only">操作</span>
                </div>
                {papers.map(p => (
                  <article
                    className={`paper-row ${selected.includes(p.id) ? 'is-selected' : ''}`}
                    key={p.id}
                  >
                    <input
                      type="checkbox"
                      aria-label={`选择 ${p.title}`}
                      checked={selected.includes(p.id)}
                      onChange={e =>
                        setSelected(ids =>
                          e.target.checked ? [...ids, p.id] : ids.filter(id => id !== p.id)
                        )
                      }
                    />
                    <div className="paper-identity">
                      <button className="paper-title" onClick={() => openPaper(p)}>
                        {p.title}
                      </button>
                      <p>
                        {p.authors?.length ? p.authors.join(', ') : '作者待补充'}
                        <span> · {p.year || '年份待补充'}</span>
                      </p>
                      {!!p.knowledge_bases?.length && (
                        <small>{p.knowledge_bases.map((b: Row) => b.name).join(' / ')}</small>
                      )}
                    </div>
                    <div className="paper-tags">
                      {(p.tags || []).slice(0, 2).map((t: string) => (
                        <button
                          className="tag"
                          key={t}
                          onClick={() => navigate({ ...route, tag: t, offset: 0 })}
                        >
                          {t}
                        </button>
                      ))}
                      {p.tags?.length > 2 && (
                        <span title={p.tags.slice(2).join('、')}>+{p.tags.length - 2}</span>
                      )}
                    </div>
                    <span className={`paper-availability ${p.active_version ? '' : 'pending'}`}>
                      {p.active_version ? (
                        <>
                          <Check size={13} /> {p.page_count} 页
                        </>
                      ) : (
                        '待补 PDF'
                      )}
                    </span>
                    <button
                      className="icon-button quiet row-action"
                      disabled={busy}
                      title={archived ? '恢复到文献库' : '归档论文'}
                      aria-label={`${archived ? '恢复' : '归档'} ${p.title}`}
                      onClick={() =>
                        void mutate(async () => {
                          await api(
                            `/papers/${p.id}${archived ? '/restore' : ''}`,
                            archived ? 'POST' : 'DELETE'
                          )
                          notify(archived ? '已恢复到文献库' : '已归档，可在「已归档」中恢复')
                        })
                      }
                    >
                      {archived ? <ArrowDownToLine size={16} /> : <Archive size={16} />}
                    </button>
                  </article>
                ))}
              </div>
            )
          )}
          {!loading && !error && (
            <div className="list-footer">
              <span>
                {total ? `${offset + 1}–${Math.min(offset + 20, total)} / ${total} 篇` : '0 篇论文'}
              </span>
              <div>
                <button
                  className="quiet"
                  aria-label="上一页文献"
                  disabled={!offset}
                  onClick={() => navigate({ ...route, offset: Math.max(0, offset - 20) })}
                >
                  <ChevronLeft size={16} />
                  上一页
                </button>
                <button
                  className="quiet"
                  aria-label="下一页文献"
                  disabled={offset + 20 >= total}
                  onClick={() => navigate({ ...route, offset: offset + 20 })}
                >
                  下一页
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  )
}
