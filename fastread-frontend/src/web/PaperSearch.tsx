import { useEffect, useRef, useState } from 'react'
import { Alert, Button, PanelHeader, Section, Select, TextField, Toolbar } from '@fastrd/ui-react'
import { ArrowLeft, Search } from 'lucide-react'
import type { Job } from './Organize'

type Row = Record<string, any>
export default function PaperSearch({
  api,
  submit,
  jobs,
  books,
  target,
  onTarget,
  onBack,
  onJobs,
}: {
  api: (path: string, method?: string, body?: unknown) => Promise<any>
  submit: (path: string, body?: unknown) => Promise<Job>
  jobs: Job[]
  books: Row[]
  target: string
  onTarget: (id: string) => void
  onBack: () => void
  onJobs: () => void
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Row | null>(null)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')
  const [imports, setImports] = useState<
    Record<string, { job?: Job; pending?: boolean; error?: string }>
  >({})
  const generation = useRef(0)
  useEffect(
    () => () => {
      generation.current++
    },
    []
  )
  async function search() {
    if (searching || !query.trim()) return
    const current = ++generation.current
    setSearching(true)
    setError('')
    setResults(null)
    try {
      const value = await api('/search', 'POST', { query: query.trim() })
      if (generation.current === current) setResults(value)
    } catch (failure) {
      if (generation.current === current) setError((failure as Error).message)
    } finally {
      if (generation.current === current) setSearching(false)
    }
  }
  async function importPaper(url: string) {
    if (imports[url]?.pending) return
    setImports(value => ({ ...value, [url]: { pending: true } }))
    try {
      const job = await submit('/imports/url', { url })
      setImports(value => ({ ...value, [url]: { job } }))
    } catch (failure) {
      setImports(value => ({ ...value, [url]: { error: (failure as Error).message } }))
    }
  }
  return (
    <Section className="paper-search-page app-page" aria-label="搜索论文">
      <PanelHeader className="app-page-heading">
        <h1 className="fastui-heading m-0 text-2xl">搜索论文</h1>
        <Button variant="quiet" aria-label="返回阅读" onClick={onBack}>
          <ArrowLeft size={18} />
          返回阅读
        </Button>
      </PanelHeader>
      <form
        id="library-search"
        className="paper-search-form"
        onSubmit={event => {
          event.preventDefault()
          void search()
        }}
      >
        <label className="fastui-field">
          搜索公开论文
          <TextField
            name="query"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="论文标题、DOI 或关键词"
            required
            autoFocus
          />
        </label>
        <Button
          type="submit"
          variant="primary"
          disabled={searching || !query.trim()}
          loading={searching}
        >
          <Search size={17} />
          {searching ? '搜索中' : '搜索'}
        </Button>
      </form>
      <label className="fastui-field paper-search-target">
        导入到知识库
        <Select
          value={target}
          onChange={event => onTarget(event.target.value)}
          aria-label="搜索结果导入知识库"
        >
          <option value="">自动归类</option>
          {books.map(book => (
            <option key={book.id} value={book.id}>
              {book.name}
            </option>
          ))}
        </Select>
      </label>
      {error && <Alert tone="danger">{error}</Alert>}
      <div aria-live="polite" role="status">
        {searching
          ? '正在检索公开来源…'
          : results
            ? `找到 ${results.papers?.length || 0} 篇论文`
            : ''}
      </div>
      {results && (
        <>
          {Object.entries(results.sources || {}).some(
            ([, status]) => !(status as Row).available
          ) && (
            <Alert tone="warning">
              部分来源暂不可用：
              {Object.entries(results.sources || {})
                .filter(([, status]) => !(status as Row).available)
                .map(([name]) => name)
                .join('、')}
            </Alert>
          )}
          {!results.papers?.length && (
            <p className="reading-muted">没有找到匹配的论文，试试其他标题、DOI 或关键词。</p>
          )}
          {(results.papers || []).map((paper: Row, index: number) => {
            const url =
              paper.pdf_url ||
              paper.url ||
              paper.source_url ||
              (paper.doi ? `https://doi.org/${paper.doi}` : '')
            const imported = imports[url]
            const job = jobs.find(item => item.id === imported?.job?.id) || imported?.job
            const retry = job?.state === 'failed' || job?.state === 'cancelled'
            return (
              <Section
                className="paper-search-result app-flat-section grid gap-3"
                key={`${paper.id || url}-${index}`}
              >
                <h2 className="fastui-heading m-0 text-base">{paper.title}</h2>
                <p className="reading-muted m-0">
                  {paper.authors?.join(', ')}
                  {paper.year ? ` · ${paper.year}` : ''}
                </p>
                {paper.doi && <small>DOI: {paper.doi}</small>}
                {paper.identity_warning && <Alert tone="warning">{paper.identity_warning}</Alert>}
                {paper.abstract && <p className="m-0">{paper.abstract.slice(0, 500)}</p>}
                <Toolbar label="搜索结果操作">
                  {url && (
                    <a className="fastui-link" href={url} target="_blank" rel="noreferrer">
                      查看来源
                    </a>
                  )}
                  <Button
                    disabled={!url || imported?.pending || Boolean(job && !retry)}
                    loading={imported?.pending}
                    onClick={() => void importPaper(url)}
                  >
                    {job?.state === 'succeeded'
                      ? '已导入'
                      : job?.state === 'needs_attention'
                        ? '需要处理'
                        : job && !retry
                          ? '导入中'
                          : retry
                            ? '重新导入'
                            : '导入这篇论文'}
                  </Button>
                  {job && (
                    <Button variant="quiet" onClick={onJobs}>
                      查看任务
                    </Button>
                  )}
                </Toolbar>
                {(imported?.error || job?.error) && (
                  <Alert tone="danger">{imported?.error || job?.error}</Alert>
                )}
              </Section>
            )
          })}
        </>
      )}
    </Section>
  )
}
