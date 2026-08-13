import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  BookOpenCheck,
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
  list_search_venues,
  search_papers,
  type PaperSearchResponse,
  type PaperSearchResult,
  type SearchVenue,
} from '@/services/note'
import { useModelStore } from '@/store/modelStore'
import { useTaskStore } from '@/store/taskStore'
import { cn } from '@/lib/utils'

type Track = 'security' | 'systems'

const TRACK_LABEL: Record<Track, string> = {
  security: '安全四大',
  systems: '系统顶会',
}

function VenueChip({ venue }: { venue: SearchVenue }) {
  const isSecurity = venue.track === 'security'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-[11px] font-medium',
        isSecurity
          ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
          : 'border-blue-200 bg-blue-50 text-blue-800',
      )}
    >
      <ShieldCheck className="h-3 w-3" />
      {venue.short_name}
    </span>
  )
}

function ResultCard({
  paper,
  onImport,
  importing,
}: {
  paper: PaperSearchResult
  onImport: (paper: PaperSearchResult) => void
  importing: boolean
}) {
  const link = paper.pdf_url || paper.source_url
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-[15px] font-semibold leading-6 text-slate-900">{paper.title}</h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <VenueChip venue={paper.venue} />
            {paper.year && <span className="font-mono">{paper.year}</span>}
            {paper.authors.length > 0 && (
              <span className="truncate">
                {paper.authors.slice(0, 3).join('、')}
                {paper.authors.length > 3 ? ' 等' : ''}
              </span>
            )}
            <span className="font-mono text-slate-400">rel {paper.relevance}</span>
          </div>
        </div>
      </div>

      {paper.abstract && (
        <p className="mt-3 line-clamp-3 text-[13px] leading-6 text-slate-600">{paper.abstract}</p>
      )}

      {paper.keywords.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {paper.keywords.slice(0, 8).map(kw => (
            <span
              key={kw}
              className="rounded-sm bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600"
            >
              {kw}
            </span>
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => onImport(paper)} disabled={importing}>
          {importing ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <BookOpenCheck className="mr-1.5 h-3.5 w-3.5" />
          )}
          导入并阅读
        </Button>
        {link && (
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-slate-500 underline underline-offset-4 hover:text-slate-800"
          >
            原文 <ExternalLink className="h-3 w-3" />
          </a>
        )}
        {paper.doi && (
          <a
            href={`https://doi.org/${paper.doi}`}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-[11px] text-slate-400 hover:text-slate-700"
          >
            {paper.doi}
          </a>
        )}
      </div>
    </article>
  )
}

const SearchPage = () => {
  const navigate = useNavigate()
  const { modelList, loadEnabledModels } = useModelStore()
  const { addPendingTask, setCurrentTask, updateTaskContent } = useTaskStore()

  const [query, setQuery] = useState('')
  const [tracks, setTracks] = useState<Track[]>(['security', 'systems'])
  const [venues, setVenues] = useState<SearchVenue[]>([])
  const [selectedVenues, setSelectedVenues] = useState<string[]>([])
  const [response, setResponse] = useState<PaperSearchResponse | null>(null)
  const [searching, setSearching] = useState(false)
  const [importingId, setImportingId] = useState('')
  const [showUnconfirmed, setShowUnconfirmed] = useState(false)

  useEffect(() => {
    loadEnabledModels()
    list_search_venues()
      .then(data => setVenues(data.venues || []))
      .catch(() => setVenues([]))
  }, [loadEnabledModels])

  const visibleVenues = useMemo(
    () => venues.filter(v => tracks.includes(v.track as Track)),
    [venues, tracks],
  )

  const toggleTrack = (track: Track) => {
    setTracks(prev => {
      const next = prev.includes(track) ? prev.filter(t => t !== track) : [...prev, track]
      return next.length ? next : prev
    })
  }

  const toggleVenue = (id: string) => {
    setSelectedVenues(prev => (prev.includes(id) ? prev.filter(v => v !== id) : [...prev, id]))
  }

  const runSearch = async () => {
    const cleaned = query.trim()
    if (!cleaned) {
      toast.error('请输入检索关键词')
      return
    }
    setSearching(true)
    try {
      const data = await search_papers({
        query: cleaned,
        tracks,
        venue_ids: selectedVenues,
        limit: 20,
        include_unconfirmed: true,
      })
      setResponse(data)
      if (data.result_count === 0) {
        toast('没有命中允许会议的论文，可展开"未确认会议"查看被排除的结果', { icon: 'ℹ️' })
      }
    }
    catch {
      toast.error('检索失败，请稍后再试')
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
    if (!url) {
      toast.error('该论文没有可访问的原文链接')
      return
    }
    setImportingId(paper.id)
    try {
      const snapshot = await ingest_paper_url({
        url,
        provider_id: model.provider_id,
        model_name: model.model_name,
        title: paper.title,
        authors: paper.authors,
        venue: paper.venue.short_name || paper.journal_ref,
        doi: paper.doi,
        year: paper.year ?? undefined,
      })
      addPendingTask(snapshot.id, 'paper', {
        video_url: url,
        platform: 'paper',
        input_mode: 'paper',
        model_name: model.model_name,
        provider_id: model.provider_id,
      })
      updateTaskContent(snapshot.id, {
        status: snapshot.status,
        message: snapshot.message,
        transcript: snapshot.result?.transcript || snapshot.transcript,
        audioMeta: snapshot.result?.audioMeta || snapshot.audioMeta,
        insights: snapshot.result?.insights || snapshot.insights,
      })
      setCurrentTask(snapshot.id)
      toast.success('论文已导入，正在进入阅读工作台')
      navigate('/workspace')
      window.dispatchEvent(
        new CustomEvent('fastread:workspace-command', {
          detail: { viewMode: 'report', chat: false },
        }),
      )
    }
    catch {
      toast.error('导入失败，该论文可能未提供可解析的正文或 PDF')
    }
    finally {
      setImportingId('')
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
          <Link to="/" className="flex items-center gap-3">
            <img src={logo} alt="FastRead" className="h-8 w-8" />
            <div>
              <div className="text-sm font-semibold text-slate-900">论文检索</div>
              <div className="text-[11px] text-slate-500">只搜安全四大与系统顶会</div>
            </div>
          </Link>
          <Button variant="outline" size="sm" onClick={() => navigate('/')}>
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" />
            返回资料库
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-5 px-6 py-6 pb-16">
        {/* search box */}
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') runSearch()
                }}
                placeholder="输入安全/系统方向关键词，例如 side-channel、prompt injection、kernel isolation"
                className="pl-9"
              />
            </div>
            <Button onClick={runSearch} disabled={searching} className="sm:w-32">
              {searching ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Search className="mr-1.5 h-4 w-4" />}
              {searching ? '检索中…' : '检索'}
            </Button>
          </div>

          {/* track filter */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              范围
            </span>
            {(['security', 'systems'] as Track[]).map(track => (
              <button
                key={track}
                type="button"
                onClick={() => toggleTrack(track)}
                className={cn(
                  'rounded-sm border px-2 py-1 text-xs font-medium transition',
                  tracks.includes(track)
                    ? 'border-slate-900 bg-slate-900 text-white'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300',
                )}
              >
                {TRACK_LABEL[track]}
              </button>
            ))}
          </div>

          {/* venue filter */}
          {visibleVenues.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                会议
              </span>
              {visibleVenues.map(venue => (
                <button
                  key={venue.id}
                  type="button"
                  title={venue.name}
                  onClick={() => toggleVenue(venue.id)}
                  className={cn(
                    'rounded-sm border px-1.5 py-0.5 text-[11px] transition',
                    selectedVenues.includes(venue.id)
                      ? 'border-slate-900 bg-slate-100 font-medium text-slate-900'
                      : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300',
                  )}
                >
                  {venue.short_name}
                </button>
              ))}
              {selectedVenues.length > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedVenues([])}
                  className="ml-1 text-[11px] text-slate-400 underline underline-offset-2 hover:text-slate-700"
                >
                  清除
                </button>
              )}
            </div>
          )}
        </section>

        {/* coverage disclosure — never let a thin result set look exhaustive */}
        {response && (
          <section className="rounded-md border border-amber-200 bg-amber-50 p-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
              <div className="min-w-0 text-xs leading-5 text-amber-900">
                <div className="font-semibold">检索覆盖范围说明</div>
                <p className="mt-0.5">{response.coverage_note}</p>
                <div className="mt-1.5 flex flex-wrap gap-3 font-mono text-[11px] text-amber-800">
                  <span className="inline-flex items-center gap-1">
                    <Database className="h-3 w-3" />
                    {response.search_backend}
                  </span>
                  <span>索引 {response.index_stats.documents} 篇 / {response.index_stats.terms} 词</span>
                  <span>本次抓取 {response.fetched_this_run} 篇</span>
                  <span>命中 {response.result_count} 篇</span>
                  <span>会议未确认 {response.venue_unconfirmed_count} 篇</span>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* results */}
        {response && (
          <section className="space-y-3">
            {response.results.map(paper => (
              <ResultCard
                key={paper.id}
                paper={paper}
                onImport={handleImport}
                importing={importingId === paper.id}
              />
            ))}
            {response.result_count === 0 && (
              <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
                没有命中允许会议的论文。可以换关键词，或展开下方"未确认会议"的结果自行判断。
              </div>
            )}
          </section>
        )}

        {/* excluded papers, shown explicitly rather than silently dropped */}
        {response && response.venue_unconfirmed.length > 0 && (
          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <button
              type="button"
              onClick={() => setShowUnconfirmed(v => !v)}
              className="flex w-full items-center justify-between text-left"
            >
              <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                未确认会议（已排除，{response.venue_unconfirmed.length} 篇）
              </span>
              <span className="text-xs text-slate-400">{showUnconfirmed ? '收起' : '展开'}</span>
            </button>
            {showUnconfirmed && (
              <div className="mt-3 space-y-3 border-t border-slate-200 pt-3">
                <p className="text-[11px] leading-5 text-slate-500">
                  这些论文命中了关键词，但 comments / journal_ref 中没有可确认的会议信息，因此没有计入正式结果。
                </p>
                {response.venue_unconfirmed.map(paper => (
                  <div key={paper.id} className="rounded-md border border-slate-200 bg-slate-50 p-3">
                    <div className="text-[13px] font-medium text-slate-800">{paper.title}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                      {paper.year && <span className="font-mono">{paper.year}</span>}
                      <span>{paper.authors.slice(0, 2).join('、')}</span>
                      {(paper.pdf_url || paper.source_url) && (
                        <a
                          href={paper.pdf_url || paper.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 underline underline-offset-2 hover:text-slate-800"
                        >
                          原文 <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {!response && !searching && (
          <section className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
            <Search className="mx-auto h-8 w-8 text-slate-300" />
            <h2 className="mt-3 text-base font-semibold text-slate-900">搜索安全与系统顶会论文</h2>
            <p className="mx-auto mt-1.5 max-w-lg text-sm leading-6 text-slate-500">
              结果限定在 IEEE S&amp;P、USENIX Security、ACM CCS、NDSS 四大安全会议，
              以及 OSDI、SOSP、ASPLOS、EuroSys、USENIX ATC、SIGCOMM 等系统顶会。
              命中后可一键导入，直接生成关键问题阅读报告。
            </p>
          </section>
        )}
      </main>
    </div>
  )
}

export default SearchPage
