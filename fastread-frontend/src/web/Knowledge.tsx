import {
  AssetCard,
  EmptyState,
  Button,
  Checkbox,
  InspectorSection,
  PanelHeader,
  Section,
  Select,
  TextArea,
  TextField,
  Toolbar,
} from '@fastrd/ui-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from './Markdown'
import { OrganizeButton } from './Organize'
import IntegrationActions from './Integrations'
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
export function PaperTools({
  paper,
  books,
  api,
  action,
  providerId,
  model,
  onTag,
  reload,
}: Props & {
  paper: Row
  books: Row[]
  onTag: (tag: string) => void
  reload: () => Promise<void>
}) {
  const sourceTags = (paper.tags || []).join(', ')
  const [tags, setTags] = useState<string>(sourceTags)
  const [bookId, setBookId] = useState('')
  useEffect(() => setTags(sourceTags), [paper.id, sourceTags])
  return (
    <Section className="paper-tools grid gap-3 p-4">
      <div className="tag-row flex flex-wrap gap-2">
        {(paper.tags || []).map((tag: string) => (
          <Button
            className="tag"
            key={tag}
            onClick={() => onTag(tag)}
            type="button"
            variant="quiet"
          >
            # {tag}
          </Button>
        ))}
      </div>
      {paper.principle && (
        <div className="principle grid gap-2">
          <p className="m-0 leading-relaxed break-words">{paper.principle}</p>
        </div>
      )}
      <Toolbar className="toolbar" label="操作">
        <label className="fastui-field">
          归入知识库
          <Select
            aria-label="归入知识库"
            value={bookId}
            onChange={e => setBookId(e.target.value)}
            className="w-full"
          >
            <option value="">让 AI 自动判断</option>
            {books.map(b => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </Select>
        </label>
        <OrganizeButton
          ids={[paper.id]}
          disabled={!providerId}
          body={{ provider_id: providerId, model, knowledge_id: bookId }}
          label="智能整理原理与标签"
        />
        {bookId && (
          <Button
            className="quiet"
            onClick={() =>
              void action(async () => {
                await api(`/knowledge-bases/${bookId}/papers`, 'POST', { paper_ids: [paper.id] })
                await reload()
              })
            }
            type="button"
            variant="quiet"
          >
            直接加入
          </Button>
        )}
      </Toolbar>
      <InspectorSection label="编辑标签与知识库归属">
        <form
          onSubmit={e => {
            e.preventDefault()
            void action(async () => {
              await api(`/papers/${paper.id}/tags`, 'PUT', {
                tags: tags
                  .split(/[,，]/)
                  .map(t => t.trim())
                  .filter(Boolean),
              })
              await reload()
            })
          }}
          className="inline-form flex grid min-w-0 flex-wrap items-end gap-3"
        >
          <label className="fastui-field">
            多个标签，用逗号分隔
            <TextField
              aria-label="论文标签"
              value={tags}
              onChange={e => setTags(e.target.value)}
              maxLength={800}
              className="w-full"
            />
          </label>
          <Button type="submit" variant="primary">
            保存标签
          </Button>
        </form>
        <div className="tag-row flex flex-wrap gap-2">
          {(paper.knowledge_bases || []).map((b: Row) => (
            <Button
              className="quiet"
              key={b.id}
              onClick={() =>
                void action(async () => {
                  await api(`/knowledge-bases/${b.id}/papers/${paper.id}`, 'DELETE')
                  await reload()
                })
              }
              type="button"
              variant="quiet"
            >
              {b.name} · 移出
            </Button>
          ))}
        </div>
      </InspectorSection>
    </Section>
  )
}
export default function Knowledge(
  props: Props & {
    initialTag?: string
    onOpenBook?: (id: string) => void
  }
) {
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
  useEffect(() => {
    setTag(props.initialTag || '')
    setBookId('')
    setOffset(0)
  }, [props.initialTag])
  const requestNumber = useRef(0)
  const reload = useCallback(
    async (signal?: AbortSignal) => {
      const request = ++requestNumber.current
      const [libraries, allTags] = await Promise.all([api('/knowledge-bases'), api('/tags')])
      if (signal?.aborted || request !== requestNumber.current) return
      setBooks(libraries.items)
      setTags(allTags.items)
      if (bookId) {
        const [detail, history] = await Promise.all([
          api(`/knowledge-bases/${bookId}`),
          api(`/knowledge-bases/${bookId}/messages`),
        ])
        if (signal?.aborted || request !== requestNumber.current) return
        setBook(detail)
        setPapers(detail.papers)
        setTotal(detail.papers.length)
        setMessages(history.items)
      } else {
        const result = await api(`/papers?limit=20&offset=${offset}&tag=${encodeURIComponent(tag)}`)
        if (signal?.aborted || request !== requestNumber.current) return
        setBook(null)
        setPapers(result.items)
        setTotal(result.total)
      }
    },
    [api, bookId, offset, tag]
  )
  useEffect(() => {
    const controller = new AbortController()
    void action(() => reload(controller.signal))
    return () => controller.abort()
  }, [action, reload, revision])
  useEffect(() => {
    setSelected([])
    setQuestion('')
  }, [bookId, tag, offset])
  function chooseTag(value: string) {
    setTag(value)
    setBookId('')
    setOffset(0)
  }
  async function ask() {
    setBusy(true)
    try {
      await submitJob(`/knowledge-bases/${bookId}/messages`, {
        content: question,
        provider_id: providerId,
        model,
      })
      setQuestion('')
      await reload()
    } finally {
      setBusy(false)
    }
  }
  const columns = [...new Set(papers.flatMap(p => p.tags || []))].slice(0, 16) as string[]
  return (
    <Section className="knowledge-home grid gap-6 p-5 sm:p-6">
      <div className="knowledge-hero flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="fastui-heading m-0 text-xl">论文库</h1>
          <p className="m-0 leading-relaxed break-words">阅读、归类、追问。</p>
        </div>
        <Button onClick={() => setCreating(!creating)} type="button" variant="primary">
          新建知识库
        </Button>
      </div>
      {creating && (
        <form
          onSubmit={e => {
            e.preventDefault()
            const f = e.currentTarget
            void action(async () => {
              const result = await api(
                '/knowledge-bases',
                'POST',
                Object.fromEntries(new FormData(f))
              )
              setBookId(result.id)
              props.onOpenBook?.(result.id)
              setCreating(false)
              f.reset()
            })
          }}
          className="create-book grid min-w-0 gap-4 p-4"
        >
          <label className="fastui-field">
            名称
            <TextField
              name="name"
              placeholder="例如：大模型推理与检索"
              maxLength={80}
              required
              className="w-full"
            />
          </label>
          <label className="fastui-field">
            关注的问题
            <TextField
              name="description"
              placeholder="研究问题（可选）"
              maxLength={1000}
              className="w-full"
            />
          </label>
          <Button type="submit" variant="primary">
            创建知识库
          </Button>
        </form>
      )}
      <nav
        className="book-grid grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3"
        aria-label="知识库目录"
      >
        <AssetCard
          label="全部论文"
          description={`${total} 篇`}
          className="!p-3"
          selected={!bookId && !tag}
          onClick={() => {
            setBookId('')
            setTag('')
            setOffset(0)
          }}
        />
        {books.map(b => (
          <AssetCard
            key={b.id}
            className="!p-3"
            label={b.name}
            description={`${b.paper_count} 篇${b.description ? ` · ${b.description.slice(0, 80)}` : ['queued', 'running'].includes(b.questions_status) ? ' · 生成研究问题中…' : ''}`}
            selected={bookId === b.id}
            onClick={() => {
              if (props.onOpenBook) props.onOpenBook(b.id)
              else {
                setBookId(b.id)
                setTag('')
                setOffset(0)
              }
            }}
          />
        ))}
      </nav>
      <PanelHeader className="section-heading">
        <div>
          <h2 className="fastui-heading m-0 text-base">
            {book?.name || (tag ? `标签：${tag}` : '我的论文')}
          </h2>
          <p className="m-0 leading-relaxed break-words">{book?.description || `${total} 篇`}</p>
        </div>
        <Button className="quiet" onClick={() => setMatrix(!matrix)} type="button" variant="quiet">
          {matrix ? '卡片视图' : '关系矩阵'}
        </Button>
      </PanelHeader>
      {book && !book.description && (
        <p className="m-0 leading-relaxed break-words">
          <Button
            className="quiet"
            disabled={['queued', 'running'].includes(
              books.find(b => b.id === bookId)?.questions_status
            )}
            onClick={() =>
              void action(async () => {
                await api(`/knowledge-bases/${bookId}/questions`, 'POST')
                await reload()
              })
            }
            type="button"
            variant="quiet"
          >
            {['queued', 'running'].includes(books.find(b => b.id === bookId)?.questions_status)
              ? 'AI 正在生成关注的问题…'
              : '生成关注的问题'}
          </Button>
        </p>
      )}
      {!!tags.length && (
        <div className="tag-row flex flex-wrap gap-2">
          <Button
            className="tag"
            aria-pressed={!tag}
            onClick={() => chooseTag('')}
            type="button"
            variant="quiet"
          >
            全部标签
          </Button>
          {tags.slice(0, 30).map(t => (
            <Button
              key={t.tag}
              className="tag"
              aria-pressed={tag === t.tag}
              onClick={() => chooseTag(t.tag)}
              type="button"
              variant="quiet"
            >
              # {t.tag} <small className="text-xs">{t.paper_count}</small>
            </Button>
          ))}
        </div>
      )}
      <Toolbar label="论文批量操作" className="selection-bar">
        <span className="inline-flex h-7 shrink-0 items-center">已选 {selected.length} 篇</span>
        <Select
          aria-label="所选论文加入知识库"
          value={target}
          onChange={e => setTarget(e.target.value)}
          className="w-auto"
        >
          <option value="">选择知识库</option>
          {books.map(b => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </Select>
        <Button
          className="quiet"
          disabled={!selected.length || !target}
          onClick={() =>
            void action(async () => {
              await api(`/knowledge-bases/${target}/papers`, 'POST', { paper_ids: selected })
              setSelected([])
              await reload()
            })
          }
          type="button"
          variant="quiet"
        >
          加入知识库
        </Button>
        <OrganizeButton
          ids={selected}
          disabled={
            !providerId || selected.some(id => !papers.find(p => p.id === id)?.active_version)
          }
          body={{ provider_id: providerId, model, knowledge_id: target }}
          label="AI 整理"
        />
        <IntegrationActions api={api} paperIds={selected} providerId={providerId} model={model} />
      </Toolbar>
      {matrix ? (
        <div
          className="matrix-scroll fastui-table-scroll"
          role="region"
          aria-label="论文关系矩阵"
          tabIndex={0}
        >
          <p className="muted m-0 text-sm leading-relaxed break-words">
            论文 × 研究标签。圆点表示共享标签，不代表因果关系。
          </p>
          <table className="relation-matrix fastui-table w-full">
            <thead>
              <tr>
                <th>论文</th>
                {columns.map(t => (
                  <th key={t}>
                    <Button
                      className="tag"
                      onClick={() => chooseTag(t)}
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
              {papers.map(p => (
                <tr key={p.id}>
                  <th>
                    <Button
                      className="quiet"
                      onClick={() => void action(() => openPaper(p.id))}
                      type="button"
                      variant="quiet"
                    >
                      {p.title}
                    </Button>
                  </th>
                  {columns.map(t => (
                    <td key={t}>
                      {p.tags?.includes(t) ? <span aria-label="包含此标签">●</span> : '—'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {!columns.length && (
            <p className="m-0 leading-relaxed break-words">
              先智能整理或手动添加标签，即可查看关系矩阵。
            </p>
          )}
        </div>
      ) : (
        <div className="knowledge-papers grid grid-cols-1 gap-4 xl:grid-cols-2">
          {papers.map(p => (
            <article
              key={p.id}
              className="knowledge-paper fastui-section grid min-w-0 content-start gap-4 p-5"
            >
              <div className="card-top flex flex-wrap items-center justify-between gap-2">
                <label className="selection-label fastui-field">
                  <Checkbox
                    aria-label={`选择论文 ${p.title}`}
                    checked={selected.includes(p.id)}
                    onChange={e =>
                      setSelected(current =>
                        e.target.checked ? [...current, p.id] : current.filter(id => id !== p.id)
                      )
                    }
                  />
                </label>
                <small className="text-xs">
                  {p.metadata?.year || p.year || '年份待核实'} ·{' '}
                  {p.metadata?.page_count || p.page_count || '?'} 页
                </small>
              </div>
              <h3 className="fastui-heading m-0 text-sm">
                <Button
                  className="paper-title h-auto text-left whitespace-normal"
                  onClick={() => void action(() => openPaper(p.id))}
                  type="button"
                  variant="quiet"
                >
                  {p.title}
                </Button>
              </h3>
              <div className="principle grid gap-2">
                <p className="m-0 leading-relaxed break-words">{p.principle || '尚未整理'}</p>
              </div>
              <div className="tag-row flex flex-wrap gap-2">
                {p.tags?.map((t: string) => (
                  <Button
                    key={t}
                    className="tag"
                    onClick={() => chooseTag(t)}
                    type="button"
                    variant="quiet"
                  >
                    # {t}
                  </Button>
                ))}
              </div>
              <Toolbar className="toolbar" label="操作">
                <Button
                  className="quiet"
                  onClick={() => void action(() => openPaper(p.id))}
                  type="button"
                  variant="quiet"
                >
                  阅读原文
                </Button>
                <OrganizeButton
                  ids={[p.id]}
                  disabled={!providerId || !p.active_version}
                  body={{ provider_id: providerId, model, knowledge_id: bookId }}
                />
                {bookId && (
                  <Button
                    className="quiet"
                    onClick={() =>
                      void action(async () => {
                        await api(`/knowledge-bases/${bookId}/papers/${p.id}`, 'DELETE')
                        await reload()
                      })
                    }
                    type="button"
                    variant="quiet"
                  >
                    移出
                  </Button>
                )}
              </Toolbar>
              {!!p.principle_evidence?.length && (
                <InspectorSection label="原理的原文依据">
                  {p.principle_evidence.map((s: Row, i: number) => (
                    <blockquote
                      key={i}
                      className="fastui-section m-0 max-h-48 overflow-auto p-3 break-words"
                    >
                      <Button
                        className="page-link"
                        onClick={() =>
                          void action(() => openPaper(s.paper_id, s.page, s.version_id))
                        }
                        type="button"
                        variant="quiet"
                      >
                        第 {s.page} 页
                      </Button>{' '}
                      {s.quote}
                    </blockquote>
                  ))}
                </InspectorSection>
              )}
            </article>
          ))}
        </div>
      )}
      {!papers.length && (
        <EmptyState title={book ? '把论文放进来，开始建立联系' : '从第一篇论文开始'}>
          <p className="m-0 leading-relaxed break-words">
            {book ? '添加论文以开始阅读。' : '上传 PDF 或导入链接。'}
          </p>
        </EmptyState>
      )}
      {!bookId && total > 20 && (
        <div className="pagination flex flex-wrap items-center justify-between gap-2">
          <Button
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 20))}
            type="button"
            variant="primary"
          >
            上一页
          </Button>
          <span>
            {offset + 1}–{Math.min(total, offset + 20)} / {total}
          </span>
          <Button
            disabled={offset + 20 >= total}
            onClick={() => setOffset(offset + 20)}
            type="button"
            variant="primary"
          >
            下一页
          </Button>
        </div>
      )}
      {book && (
        <Section className="knowledge-chat grid gap-4 p-4">
          <PanelHeader className="section-heading">
            <div>
              <h2 className="fastui-heading m-0 text-base">向知识库追问</h2>
              <p className="m-0 leading-relaxed break-words">
                比较原理、方法与结论，回答附论文页码。
              </p>
            </div>
          </PanelHeader>
          <div className="messages grid gap-3">
            {messages.map(m => (
              <article className={`message fastui-section min-w-0 p-4 ${m.role}`} key={m.id}>
                <b>{m.role === 'user' ? '你' : 'FastRead'}</b>
                <ReactMarkdown>{m.content}</ReactMarkdown>
                {m.evidence?.sources?.map((s: Row, i: number) => (
                  <blockquote
                    key={i}
                    className="fastui-section m-0 max-h-48 overflow-auto p-3 break-words"
                  >
                    <Button
                      className="page-link"
                      onClick={() => void action(() => openPaper(s.paper_id, s.page, s.version_id))}
                      type="button"
                      variant="quiet"
                    >
                      [{s.id}] {s.title} · 第 {s.page} 页
                    </Button>
                    <p className="m-0 leading-relaxed break-words">{s.quote}</p>
                  </blockquote>
                ))}
              </article>
            ))}
          </div>
          <form
            onSubmit={e => {
              e.preventDefault()
              void action(ask)
            }}
            className="grid min-w-0 gap-4"
          >
            <label className="fastui-field">
              你的问题
              <TextArea
                aria-label="向知识库追问"
                value={question}
                onChange={e => setQuestion(e.target.value)}
                placeholder="这些论文分别用什么机制解决问题？共同点和差异是什么？"
                maxLength={5000}
                required
                className="w-full"
              />
            </label>
            <Button
              disabled={!providerId || !papers.length || busy}
              type="submit"
              variant="primary"
            >
              {busy ? '提交中…' : '发送问题'}
            </Button>
          </form>
        </Section>
      )}
    </Section>
  )
}
