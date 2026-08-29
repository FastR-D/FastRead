import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  BookOpenCheck,
  BrainCircuit,
  Database,
  ExternalLink,
  Loader2,
  Search,
  ShieldCheck,
} from 'lucide-react'
import { toast } from 'react-hot-toast'
import logo from '@/assets/icon.png'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  ingest_paper_url,
  get_paper_index_status,
  list_search_venues,
  rebuild_paper_index,
  search_papers,
  type PaperIndexJob,
  type PaperSearchResponse,
  type PaperSearchResult,
  type ProviderHealth,
  type SearchTrack,
  type SearchVenue,
} from '@/services/note'
import { useModelStore } from '@/store/modelStore'
import { useTaskStore } from '@/store/taskStore'
import { cn } from '@/lib/utils'

const TRACK_LABEL: Record<SearchTrack, string> = {
  security: '安全四大',
  systems: '系统顶会',
  ai: 'AI 顶会',
}

const TIER_STYLE: Record<string, string> = {
  core: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  arxiv: 'border-violet-200 bg-violet-50 text-violet-800',
  scholar: 'border-amber-200 bg-amber-50 text-amber-800',
}

const PROVIDER_LABEL: Record<string, string> = {
  arxiv: 'arXiv',
  openalex: 'OpenAlex',
  semantic_scholar: 'Semantic Scholar',
  google_scholar: 'Google Scholar',
  elasticsearch: 'Elasticsearch',
}

function providerStatus(name: string, status: ProviderHealth, backend: string) {
  if (status.available) {
    const connected = status.via_proxy ? '代理已连接' : '已连接'
    return status.result_count == null ? connected : `${connected} · ${status.result_count} 条`
  }
  if (status.reason === 'proxy_required') return '需要先配置代理'
  if (status.reason === 'rate_limited') return '代理已连接 · 来源限流'
  if (name === 'google_scholar' && status.reason === 'not_configured') return '手动检索已启用 · 自动聚合需 API'
  if (name === 'elasticsearch' && backend === 'local_inverted_index') return '本机服务未启动 · 已使用内置索引'
  if (status.reason === 'deadline_exceeded') return status.via_proxy ? '经代理请求超时' : '本次连接超时'
  return '暂时不可用'
}

function formatTime(value?: string) {
  if (!value) return '尚未建立索引'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function ResultCard({
  paper,
  importing,
  onImport,
}: {
  paper: PaperSearchResult
  importing: boolean
  onImport: (paper: PaperSearchResult) => void
}) {
  const link = paper.pdf_url || paper.source_url
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={cn('rounded-sm border px-1.5 py-0.5 text-[11px] font-semibold', TIER_STYLE[paper.scope_tier])}>
              {paper.scope_label}
            </span>
            {paper.venue_confirmed && paper.venue?.short_name && (
              <span className="inline-flex items-center gap-1 rounded-sm border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[11px] text-blue-800">
                <ShieldCheck className="h-3 w-3" />
                {paper.venue.short_name}
              </span>
            )}
            <span className={`rounded-sm border px-1.5 py-0.5 text-[10px] ${paper.full_text_verified ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-slate-200 bg-slate-50 text-slate-500'}`}>
              {paper.full_text_verified ? '已导入原版 PDF · 可回到分页全文' : '发现元数据 · 全文未核验'}
            </span>
          </div>
          <h3 className="mt-2 text-[15px] font-semibold leading-6 text-slate-900">{paper.title}</h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            {paper.year && <span className="font-mono">{paper.year}</span>}
            {paper.authors?.length > 0 && (
              <span className="truncate">
                {paper.authors.slice(0, 4).join('、')}{paper.authors.length > 4 ? ' 等' : ''}
              </span>
            )}
            {typeof paper.cited_by === 'number' && <span>Scholar 引用 {paper.cited_by}</span>}
            <span className="font-mono text-slate-400">rel {paper.relevance}</span>
          </div>
        </div>
      </div>

      {paper.abstract && <p className="mt-3 line-clamp-3 text-[13px] leading-6 text-slate-600">{paper.abstract}</p>}

      {paper.keywords?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {paper.keywords.slice(0, 8).map(keyword => (
            <span key={keyword} className="rounded-sm bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">
              {keyword}
            </span>
          ))}
          <span className="px-1.5 py-0.5 text-[10px] text-slate-400">
            {paper.keyword_strategy === 'ai_abstract_keywords' ? '离线 AI 摘要关键词' : '确定性关键词回退'}
          </span>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => onImport(paper)} disabled={importing || !link}>
          {importing ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <BookOpenCheck className="mr-1.5 h-3.5 w-3.5" />}
          导入全文并阅读
        </Button>
        {link && (
          <a href={link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-slate-500 underline underline-offset-4 hover:text-slate-800">
            来源页面 <ExternalLink className="h-3 w-3" />
          </a>
        )}
        {paper.doi && (
          <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noopener noreferrer" className="font-mono text-[11px] text-slate-400 hover:text-slate-700">
            {paper.doi}
          </a>
        )}
      </div>
    </article>
  )
}

export default function SearchPage() {
  const navigate = useNavigate()
  const { modelList, loadEnabledModels } = useModelStore()
  const { applyTaskSnapshot, setCurrentTask } = useTaskStore()
  const [query, setQuery] = useState('')
  const [tracks, setTracks] = useState<SearchTrack[]>(['security', 'systems', 'ai'])
  const [venues, setVenues] = useState<SearchVenue[]>([])
  const [selectedVenues, setSelectedVenues] = useState<string[]>([])
  const [includeArxiv, setIncludeArxiv] = useState(true)
  const [includeScholar, setIncludeScholar] = useState(true)
  const [response, setResponse] = useState<PaperSearchResponse | null>(null)
  const [searching, setSearching] = useState(false)
  const [importingId, setImportingId] = useState('')
  const [indexJob, setIndexJob] = useState<PaperIndexJob | null>(null)
  const [rebuildingIndex, setRebuildingIndex] = useState(false)
  const [pageSize, setPageSize] = useState(10)
  const [currentPage, setCurrentPage] = useState(1)
  const resultsRef = useRef<HTMLElement>(null)

  useEffect(() => {
    loadEnabledModels()
    list_search_venues().then(data => setVenues(data.venues || [])).catch(() => setVenues([]))
    get_paper_index_status().then(setIndexJob).catch(() => setIndexJob(null))
  }, [loadEnabledModels])

  const visibleVenues = useMemo(
    () => venues.filter(venue => tracks.includes(venue.track as SearchTrack)),
    [tracks, venues],
  )

  const totalPages = Math.max(1, Math.ceil((response?.results.length || 0) / pageSize))
  const visibleResults = useMemo(() => {
    const start = (currentPage - 1) * pageSize
    return (response?.results || []).slice(start, start + pageSize)
  }, [currentPage, pageSize, response])

  useEffect(() => {
    if (!response) return
    requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }, [response])

  useEffect(() => {
    setCurrentPage(page => Math.min(page, totalPages))
  }, [totalPages])

  const toggleTrack = (track: SearchTrack) => {
    setTracks(current => {
      const next = current.includes(track) ? current.filter(item => item !== track) : [...current, track]
      return next.length ? next : current
    })
  }

  const runSearch = async () => {
    const cleaned = query.trim()
    if (!cleaned) {
      toast.error('请输入论文主题或自然语言问题')
      return
    }
    setSearching(true)
    try {
      const data = await search_papers({
        query: cleaned,
        tracks,
        venue_ids: selectedVenues,
        limit: 100,
        include_unconfirmed: true,
        include_arxiv: includeArxiv,
        include_scholar: includeScholar,
      })
      setResponse(data)
      setCurrentPage(1)
      if (!data.result_count) toast('当前索引与在线来源均未命中，可换一组关键词', { icon: 'ℹ️' })
    }
    catch {
      toast.error('论文检索失败，请检查网络或后端日志')
    }
    finally {
      setSearching(false)
    }
  }

  const handleImport = async (paper: PaperSearchResult) => {
    const model = modelList[0]
    if (!model) {
      toast.error('请先在设置中启用一个模型')
      return
    }
    const url = paper.pdf_url || paper.source_url
    if (!url) return
    setImportingId(paper.id)
    try {
      const snapshot = await ingest_paper_url({
        url,
        provider_id: model.provider_id,
        model_name: model.model_name,
        title: paper.title,
        authors: paper.authors,
        venue: paper.venue?.short_name || paper.journal_ref,
        doi: paper.doi,
        year: paper.year ?? undefined,
      })
      applyTaskSnapshot(snapshot, {
        source_url: url,
        model_name: model.model_name,
        provider_id: model.provider_id,
      })
      setCurrentTask(snapshot.id)
      toast.success('已导入全文；现在可以生成带页码阅读报告')
      navigate(`/workspace?task_id=${encodeURIComponent(snapshot.id)}&view=source`)
    }
    catch {
      toast.error('导入失败：该来源可能只提供元数据，未暴露可解析全文')
    }
    finally {
      setImportingId('')
    }
  }

  const handleRebuildIndex = async () => {
    const model = modelList[0]
    if (!model) {
      toast.error('请先在设置中启用一个模型')
      return
    }
    setRebuildingIndex(true)
    try {
      const job = await rebuild_paper_index({
        provider_id: model.provider_id,
        model_name: model.model_name,
        use_ai: true,
      })
      setIndexJob(job)
      if (job.search_backend === 'elasticsearch' && job.fallback_count === 0) {
        toast.success(`离线索引完成：AI ${job.ai_keyword_count} 篇，Elasticsearch ${job.elasticsearch_index_count} 篇`)
      }
      else {
        toast(`离线索引完成但存在明确降级：${job.error || `${job.fallback_count} 篇关键词回退`}`, { icon: '⚠️' })
      }
    }
    catch {
      toast.error('离线索引重建失败，请查看后端作业状态')
      get_paper_index_status().then(setIndexJob).catch(() => undefined)
    }
    finally {
      setRebuildingIndex(false)
    }
  }

  return (
    <div className="h-screen overflow-y-auto bg-slate-50">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
          <Link to="/" className="flex items-center gap-3">
            <img src={logo} alt="FastRead" className="h-8 w-8" />
            <div>
              <div className="text-sm font-semibold text-slate-900">学术论文检索</div>
              <div className="text-[11px] text-slate-500">核心顶会 + arXiv + OpenAlex + Semantic Scholar + Google Scholar</div>
            </div>
          </Link>
          <Button variant="outline" size="sm" onClick={() => navigate('/')}>
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" />返回资料库
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-5 px-6 py-6 pb-16">
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                value={query}
                onChange={event => setQuery(event.target.value)}
                onKeyDown={event => event.key === 'Enter' && runSearch()}
                placeholder="自然语言检索，例如：如何防御大模型中的间接提示注入？"
                className="pl-9"
              />
            </div>
            <Button onClick={runSearch} disabled={searching} className="sm:w-32">
              {searching ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Search className="mr-1.5 h-4 w-4" />}
              {searching ? '检索中…' : '检索'}
            </Button>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">核心范围</span>
            {(['security', 'systems', 'ai'] as SearchTrack[]).map(track => (
              <button key={track} type="button" onClick={() => toggleTrack(track)} className={cn(
                'rounded-sm border px-2 py-1 text-xs font-medium transition',
                tracks.includes(track) ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 text-slate-600',
              )}>
                {TRACK_LABEL[track]}
              </button>
            ))}
            <button type="button" onClick={() => setIncludeArxiv(value => !value)} className={cn(
              'rounded-sm border px-2 py-1 text-xs transition',
              includeArxiv ? 'border-violet-300 bg-violet-50 text-violet-800' : 'border-slate-200 text-slate-400',
            )}>arXiv 扩展</button>
            <button type="button" onClick={() => setIncludeScholar(value => !value)} className={cn(
              'rounded-sm border px-2 py-1 text-xs transition',
              includeScholar ? 'border-amber-300 bg-amber-50 text-amber-800' : 'border-slate-200 text-slate-400',
            )}>Google Scholar 补充</button>
          </div>
          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">
            arXiv、OpenAlex、Semantic Scholar 与 Google Scholar 默认启用；境内网络请先在
            <Link to="/settings/search-connections" className="mx-1 font-semibold underline underline-offset-2">学术检索连接</Link>
            填写你自己的代理地址。FastRead 不猜测端口，代理未配置时不会静默直连。
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
            <div>
              <div className="font-semibold">离线摘要关键词索引</div>
              <div className="mt-0.5 text-[11px] text-slate-500">
                {indexJob
                  ? `${indexJob.status} · AI ${indexJob.ai_keyword_count}/${indexJob.corpus_count} · ${indexJob.search_backend} · ${indexJob.prompt_version}`
                  : '尚未运行；检索按钮不会临时调用模型'}
              </div>
              {indexJob?.error && <div className="mt-0.5 max-w-3xl text-[11px] text-amber-700">明确降级原因：{indexJob.error}</div>}
            </div>
            <Button variant="outline" size="sm" onClick={handleRebuildIndex} disabled={rebuildingIndex || !modelList.length}>
              {rebuildingIndex ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Database className="mr-1.5 h-3.5 w-3.5" />}
              {rebuildingIndex ? '离线分析与 Bulk 写入中…' : '离线重建索引'}
            </Button>
          </div>

          {visibleVenues.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-slate-100 pt-3">
              <span className="mr-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">会议</span>
              {visibleVenues.map(venue => (
                <button key={venue.id} type="button" title={venue.name} onClick={() => setSelectedVenues(current => current.includes(venue.id) ? current.filter(id => id !== venue.id) : [...current, venue.id])} className={cn(
                  'rounded-sm border px-1.5 py-0.5 text-[11px]',
                  selectedVenues.includes(venue.id) ? 'border-slate-900 bg-slate-100 font-medium text-slate-900' : 'border-slate-200 text-slate-500',
                )}>
                  {venue.short_name}
                </button>
              ))}
              {selectedVenues.length > 0 && <button type="button" onClick={() => setSelectedVenues([])} className="ml-1 text-[11px] text-slate-400 underline">清除</button>}
            </div>
          )}
        </section>

        {response && (
          <section ref={resultsRef} className="scroll-mt-20 space-y-3">
            <div className="sticky top-14 z-[5] flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white/95 px-4 py-3 shadow-sm backdrop-blur">
              <div>
                <h2 className="text-sm font-semibold text-slate-900">检索结果 · {response.result_count} 篇</h2>
                <p className="mt-0.5 text-[11px] text-slate-500">
                  核心 {response.scope_counts.core} · arXiv {response.scope_counts.arxiv} · Scholar {response.scope_counts.scholar}
                  {response.result_count > 0 && ` · 当前显示 ${(currentPage - 1) * pageSize + 1}–${Math.min(currentPage * pageSize, response.result_count)}`}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
                <label className="flex items-center gap-1.5">
                  每页
                  <select
                    aria-label="每页显示数量"
                    value={pageSize}
                    onChange={event => {
                      setPageSize(Number(event.target.value))
                      setCurrentPage(1)
                    }}
                    className="rounded border border-slate-200 bg-white px-2 py-1"
                  >
                    {[10, 20, 50].map(size => <option key={size} value={size}>{size} 篇</option>)}
                  </select>
                </label>
                <span className="font-mono">{currentPage} / {totalPages}</span>
                <Button variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => setCurrentPage(page => page - 1)}>上一页</Button>
                <Button variant="outline" size="sm" disabled={currentPage >= totalPages} onClick={() => setCurrentPage(page => page + 1)}>下一页</Button>
              </div>
            </div>

            {visibleResults.map(paper => (
              <ResultCard key={paper.id} paper={paper} importing={importingId === paper.id} onImport={handleImport} />
            ))}
            {!response.result_count && (
              <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
                没有命中。下方已展开本次来源状态；也可以清除会议筛选，或换一组标题、方法和研究问题关键词。
              </div>
            )}
          </section>
        )}

        {response && (
          <details open={!response.result_count} className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950">
            <summary className="cursor-pointer select-none font-semibold">
              检索来源、时效与证据边界 · {response.search_backend} · 点击{response.result_count ? '展开' : '查看'}
            </summary>
            <div className="mt-2 flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
              <div>
                <p className="mt-0.5">{response.coverage_note}</p>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-amber-800">
                  <span className="inline-flex items-center gap-1"><Database className="h-3 w-3" />{response.search_backend}</span>
                  <span>索引 {response.index_stats.documents} 篇 / {response.index_stats.terms} 词</span>
                  <span>索引更新 {formatTime(response.index_updated_at)}</span>
                  <span>本次检索 {formatTime(response.retrieved_at)}</span>
                  <span>{response.index_stale ? '索引可能过期' : '索引时效正常'}</span>
                  <span>核心 {response.scope_counts.core} · arXiv {response.scope_counts.arxiv} · Scholar {response.scope_counts.scholar}</span>
                  <span>外部代理：{response.network_policy?.academic_proxy_configured ? '已配置，禁止直连' : '未配置，外部请求停止'}</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                  {Object.entries(response.provider_status)
                    .filter(([name]) => name in PROVIDER_LABEL)
                    .map(([name, status]) => (
                      <span key={name} className="rounded-full bg-white/70 px-2 py-0.5">
                        {PROVIDER_LABEL[name]}：{providerStatus(name, status, response.search_backend)}
                      </span>
                    ))}
                  {response.provider_status.google_scholar?.manual_search_url && (
                    <a
                      href={response.provider_status.google_scholar.manual_search_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline underline-offset-2"
                    >
                      通过系统代理在 Google Scholar 继续搜索
                    </a>
                  )}
                  <span>关键词：{response.keyword_extraction.ai_configured ? 'AI + 确定性回退' : '确定性回退（AI 未配置）'}</span>
                </div>
                {response.semantic_queries?.length ? (
                  <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] text-amber-800">
                    <span className="font-semibold">本次检索式</span>
                    {response.semantic_queries.map(item => <code key={item} className="rounded bg-white/70 px-1.5 py-0.5">{item}</code>)}
                  </div>
                ) : null}
              </div>
            </div>
          </details>
        )}

        {!response && !searching && (
          <section className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
            <BrainCircuit className="mx-auto h-9 w-9 text-slate-300" />
            <h2 className="mt-3 text-base font-semibold text-slate-900">从一个研究问题开始</h2>
            <p className="mx-auto mt-1.5 max-w-2xl text-sm leading-6 text-slate-500">
              核心层覆盖安全四大、系统顶会以及 ICLR、ICML、AAAI、NeurIPS（含旧名 NIPS）和 ACL；
              arXiv、OpenAlex 与 Semantic Scholar 扩展公开元数据，Google Scholar 在配置 API 后补充引用链与出版社版本。检索结果导入全文后才进入证据层。
            </p>
          </section>
        )}
      </main>
    </div>
  )
}
