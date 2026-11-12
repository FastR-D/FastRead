import {
  EmptyState,
  Button,
  InspectorSection,
  PanelHeader,
  Section,
  Select,
  TextField,
  Toolbar,
} from '@fastrd/ui-react'
import { useEffect, useState } from 'react'
type Row = Record<string, any>
export default function Neighbors({
  paper,
  api,
  action,
  submitJob,
  openPaper,
  revision,
  pending,
  initialTag,
}: Row) {
  const [data, setData] = useState<Row>({ papers: [], anchors: [] })
  const [tag, setTag] = useState(initialTag || ''),
    [source, setSource] = useState(''),
    [anchor, setAnchor] = useState('')
  const [year, setYear] = useState(''),
    [query, setQuery] = useState(''),
    [sort, setSort] = useState('score'),
    [page, setPage] = useState(1)
  useEffect(() => {
    let dead = false
    void action(async () => {
      const result = await api(`/papers/${paper.id}/neighbors`)
      if (!dead) setData(result)
    })
    return () => {
      dead = true
    }
  }, [api, action, paper.id, revision])
  useEffect(() => setPage(1), [tag, source, anchor, year, query, sort, data])
  const tags = [
    ...new Set<string>([
      ...(data.paper_tags || []),
      ...data.papers.flatMap((p: Row) => p.tags || []),
    ]),
  ].sort()
  const sources = [
    ...new Set<string>(data.papers.flatMap((p: Row) => p.discovery_sources || [])),
  ].sort()
  const filtered = data.papers
    .filter(
      (p: Row) =>
        (!tag || p.tags?.includes(tag)) &&
        (!source || p.discovery_sources?.includes(source)) &&
        (!anchor || p.matched_anchor_ids?.includes(anchor)) &&
        (!year || Number(p.year) >= Number(year)) &&
        (!query ||
          `${p.title} ${p.abstract || ''} ${(p.tags || []).join(' ')}`
            .toLowerCase()
            .includes(query.toLowerCase()))
    )
    .sort((a: Row, b: Row) =>
      sort === 'year'
        ? (b.year || 0) - (a.year || 0)
        : sort === 'tags'
          ? (b.shared_tags?.length || 0) - (a.shared_tags?.length || 0)
          : (b.relevance_score || 0) - (a.relevance_score || 0)
    )
  return (
    <Section className="neighbors grid gap-4 p-3">
      <PanelHeader className="section-heading">
        <div>
          <h2 className="fastui-heading m-0 text-base">近邻论文</h2>
          <p className="m-0 leading-relaxed break-words">发现相关研究。</p>
        </div>
        <Button
          disabled={pending}
          onClick={() => void action(() => submitJob(`/papers/${paper.id}/neighbors`))}
          type="button"
          variant="primary"
        >
          {pending ? '正在查找…' : data.has_snapshot ? '刷新近邻' : '查找近邻'}
        </Button>
      </PanelHeader>
      <div className="neighbor-filters grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="fastui-field">
          筛选标题或摘要
          <TextField
            aria-label="近邻关键词"
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="w-full"
          />
        </label>
        <label className="fastui-field">
          来源
          <Select value={source} onChange={e => setSource(e.target.value)} className="w-full">
            <option value="">全部来源</option>
            {sources.map(s => (
              <option key={s}>{s}</option>
            ))}
          </Select>
        </label>
        <label className="fastui-field">
          年份不早于
          <TextField
            aria-label="近邻年份"
            type="number"
            min={1900}
            max={2100}
            value={year}
            onChange={e => setYear(e.target.value)}
            className="w-full"
          />
        </label>
        <label className="fastui-field">
          排序
          <Select value={sort} onChange={e => setSort(e.target.value)} className="w-full">
            <option value="score">相关度</option>
            <option value="year">最新发表</option>
            <option value="tags">共同标签最多</option>
          </Select>
        </label>
        <Button
          className="quiet"
          onClick={() => {
            setTag('')
            setSource('')
            setAnchor('')
            setYear('')
            setQuery('')
          }}
          type="button"
          variant="quiet"
        >
          清除筛选
        </Button>
      </div>
      <div className="tag-row flex flex-wrap gap-2">
        <Button
          className="tag"
          aria-pressed={!tag}
          onClick={() => setTag('')}
          type="button"
          variant="quiet"
        >
          全部标签
        </Button>
        {tags.map(t => (
          <Button
            key={t}
            className="tag"
            aria-pressed={tag === t}
            onClick={() => setTag(tag === t ? '' : t)}
            type="button"
            variant="quiet"
          >
            {t}
          </Button>
        ))}
      </div>
      {data.anchors?.length > 0 && (
        <InspectorSection label="按检索依据筛选">
          <div className="tag-row flex flex-wrap gap-2">
            <Button
              className="tag"
              aria-pressed={!anchor}
              onClick={() => setAnchor('')}
              type="button"
              variant="quiet"
            >
              全部
            </Button>
            {data.anchors.map((a: Row, i: number) => (
              <Button
                key={a.anchor_id}
                title={a.text}
                className="tag"
                aria-pressed={anchor === a.anchor_id}
                onClick={() => setAnchor(a.anchor_id)}
                type="button"
                variant="quiet"
              >
                {{
                  research_question: '研究问题',
                  method: '方法',
                  contribution: '贡献',
                  fallback: '标题与摘要',
                }[a.kind as string] || a.kind}{' '}
                {i + 1}
              </Button>
            ))}
          </div>
        </InspectorSection>
      )}
      <p className="muted m-0 text-sm leading-relaxed break-words">
        共 {filtered.length} 篇{tag ? ` · 标签：${tag}` : ''}· 外部相关度基于题名与摘要。
      </p>
      {filtered.slice((page - 1) * 10, page * 10).map((p: Row, i: number) => (
        <article
          key={p.local_id || p.id || i}
          className="neighbor-card fastui-section grid min-w-0 gap-4 p-5"
        >
          <h3 className="fastui-heading m-0 text-sm">{p.title}</h3>
          <small className="text-xs">
            {p.year || '年份待核实'} · {(p.discovery_sources || []).join(' / ')}
            {p.relevance_score ? ` · 相关度 ${Number(p.relevance_score).toFixed(1)}` : ''}
          </small>
          <p className="m-0 leading-relaxed break-words">{p.abstract || p.principle}</p>
          <div className="tag-row flex flex-wrap gap-2">
            {(p.tags || []).map((t: string) => (
              <Button
                className="tag"
                aria-pressed={t === tag}
                key={t}
                onClick={() => setTag(t)}
                type="button"
                variant="quiet"
              >
                {t}
                {p.shared_tags?.includes(t) ? ' · 共同' : ''}
              </Button>
            ))}
          </div>
          {p.matched_terms?.length > 0 && (
            <small className="text-xs">匹配词：{p.matched_terms.join('、')}</small>
          )}
          <Toolbar className="toolbar" label="操作">
            {p.local_id ? (
              <Button
                onClick={() => void action(() => openPaper(p.local_id))}
                type="button"
                variant="primary"
              >
                阅读论文
              </Button>
            ) : (
              <>
                {(p.pdf_url || p.url || p.source_url) && (
                  <a
                    href={p.pdf_url || p.url || p.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="fastui-link break-words"
                  >
                    查看来源
                  </a>
                )}
                <Button
                  onClick={() =>
                    void action(() =>
                      submitJob('/imports/url', {
                        url: p.pdf_url || p.url || p.source_url || `https://doi.org/${p.doi}`,
                      })
                    )
                  }
                  type="button"
                  variant="primary"
                >
                  导入论文
                </Button>
              </>
            )}
          </Toolbar>
        </article>
      ))}
      {!filtered.length && (
        <EmptyState title="当前条件下没有近邻论文">
          可以清除筛选，或点击“查找近邻”检索公开论文。
        </EmptyState>
      )}
      <div className="pagination flex flex-wrap items-center justify-between gap-2">
        <Button
          className="quiet"
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
          type="button"
          variant="quiet"
        >
          上一页近邻
        </Button>
        <span>
          {page} / {Math.max(1, Math.ceil(filtered.length / 10))}
        </span>
        <Button
          className="quiet"
          disabled={page * 10 >= filtered.length}
          onClick={() => setPage(page + 1)}
          type="button"
          variant="quiet"
        >
          下一页近邻
        </Button>
      </div>
    </Section>
  )
}
