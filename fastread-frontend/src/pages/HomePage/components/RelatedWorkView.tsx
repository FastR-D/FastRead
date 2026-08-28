import { useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, ExternalLink, Loader2, Network, RefreshCw, SearchX } from 'lucide-react'
import toast from 'react-hot-toast'
import type { Task } from '@/store/taskStore'
import {
  generateRelatedWork,
  getRelatedWork,
  type RelatedWorkProviderStatus,
  type RelatedWorkSnapshot,
} from '@/services/relatedWork'
import { Button } from '@/components/ui/button'

const pageSizeOptions = [10, 20, 50, 100]

const anchorLabels: Record<string, string> = {
  research_question: '研究问题',
  method: '方法',
  contribution: '贡献',
  fallback: '标题 / 摘要',
}

function providerLabel(value: string) {
  return value
    .replace('google_scholar', 'Scholar')
    .replace('openalex', 'OpenAlex')
    .replace('paper_bibliography', '本文参考文献')
    .replace('arxiv', 'arXiv')
    .replace('elasticsearch', 'Elasticsearch')
}

function backendLabel(value: string) {
  if (value === 'local_inverted_index') return '本地论文索引'
  if (value === 'elasticsearch') return 'Elasticsearch 索引'
  return value || '论文索引'
}

function discoveryChannelLabel(value?: string) {
  if (value === 'arxiv') return '主通道 · arXiv'
  if (value === 'elasticsearch') return '主通道 · Elasticsearch'
  return '补充来源'
}

function PaginationControls({
  page,
  totalPages,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: {
  page: number
  totalPages: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
}) {
  const start = total ? (page - 1) * pageSize + 1 : 0
  const end = Math.min(page * pageSize, total)
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3">
      <div className="text-xs text-slate-600">
        显示 {start}–{end} / 共 {total} 篇 · 第 {page} / {totalPages} 页
      </div>
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-2 text-xs text-slate-600">
          每页
          <select
            aria-label="每页近邻数量"
            className="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700"
            value={pageSize}
            onChange={event => onPageSizeChange(Number(event.target.value))}
          >
            {pageSizeOptions.map(value => <option key={value} value={value}>{value} 篇</option>)}
          </select>
        </label>
        <button
          type="button"
          aria-label="上一页近邻"
          className="icon-button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        ><ChevronLeft className="h-4 w-4" /></button>
        <button
          type="button"
          aria-label="下一页近邻"
          className="icon-button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        ><ChevronRight className="h-4 w-4" /></button>
      </div>
    </div>
  )
}

type ProviderPresentation = {
  label: string
  detail: string
  className: string
}

export function describeProviderStatus(
  name: string,
  status: RelatedWorkProviderStatus,
  searchBackend: string,
): ProviderPresentation {
  const label = providerLabel(name)
  const diagnostic = status.reason || status.error || status.status || ''
  const notConfigured = status.configured === false || diagnostic === 'not_configured'

  if (diagnostic === 'proxy_required') {
    return { label, detail: '需要代理 · 当前未连接', className: 'bg-amber-50 text-amber-700' }
  }

  if (status.available) {
    const connected = status.via_proxy ? '代理已连接' : '已连接'
    if (status.result_count === 0) {
      return { label, detail: `${connected} · 暂无匹配`, className: 'bg-sky-50 text-sky-700' }
    }
    return {
      label,
      detail: status.result_count == null ? connected : `${connected} · ${status.result_count} 条候选`,
      className: 'bg-emerald-50 text-emerald-700',
    }
  }

  if (notConfigured) {
    if (name === 'google_scholar') {
      return {
        label,
        detail: status.manual_search_url ? '手动检索已启用 · 自动聚合需 API' : '自动聚合需 API',
        className: 'bg-slate-100 text-slate-600',
      }
    }
    if (name === 'elasticsearch' && searchBackend === 'local_inverted_index') {
      return { label, detail: '未启用 · 已自动使用本地索引', className: 'bg-slate-100 text-slate-600' }
    }
    return { label, detail: '未配置', className: 'bg-slate-100 text-slate-600' }
  }

  if (diagnostic === 'disabled' || diagnostic === 'refresh_disabled') {
    return { label, detail: '本次未启用', className: 'bg-slate-100 text-slate-600' }
  }
  if (diagnostic === 'deadline_exceeded') {
    return { label, detail: status.via_proxy ? '经代理请求超时 · 可重试' : '连接超时 · 可重试', className: 'bg-amber-50 text-amber-700' }
  }
  if (diagnostic === 'rate_limited') {
    return { label, detail: '代理已连接 · 来源限流', className: 'bg-amber-50 text-amber-700' }
  }
  if (name === 'elasticsearch' && searchBackend === 'local_inverted_index') {
    return { label, detail: '本机服务未启动 · 已使用内置索引', className: 'bg-slate-100 text-slate-600' }
  }
  return { label, detail: '暂时连接失败 · 可重试', className: 'bg-rose-50 text-rose-700' }
}

export default function RelatedWorkView({ task }: { task: Task | null }) {
  const [snapshot, setSnapshot] = useState<RelatedWorkSnapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [initializing, setInitializing] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  useEffect(() => {
    setSnapshot(null)
    if (!task) return
    let cancelled = false
    setInitializing(true)
    getRelatedWork(task.id)
      .then(result => { if (!cancelled) setSnapshot(result) })
      .catch(() => undefined)
      .finally(() => { if (!cancelled) setInitializing(false) })
    return () => { cancelled = true }
  }, [task])

  const anchors = useMemo(
    () => new Map((snapshot?.anchors || []).map(anchor => [anchor.anchor_id, anchor])),
    [snapshot],
  )
  const totalNeighbors = snapshot?.neighbors.length || 0
  const totalPages = Math.max(1, Math.ceil(totalNeighbors / pageSize))
  const visibleNeighbors = useMemo(
    () => (snapshot?.neighbors || []).slice((page - 1) * pageSize, page * pageSize),
    [page, pageSize, snapshot?.neighbors],
  )

  useEffect(() => {
    setPage(1)
  }, [pageSize, snapshot?.id])

  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  const run = async (force = false) => {
    if (!task) return
    setLoading(true)
    try {
      setSnapshot(await generateRelatedWork(task.id, { force, limit: 120 }))
      toast.success('近邻论文检索完成')
    }
    catch (error) {
      console.error('近邻论文检索失败', error)
      toast.error('近邻论文检索失败；请查看提供方状态后重试')
    }
    finally {
      setLoading(false)
    }
  }

  if (!task) return <div className="flex h-full items-center justify-center text-sm text-slate-500">请先导入论文。</div>
  if (!task.insights?.reading_report) {
    return (
      <div className="mx-auto max-w-3xl p-8">
        <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-10 text-center">
          <Network className="mx-auto h-9 w-9 text-slate-300" />
          <h2 className="mt-3 font-semibold text-slate-900">请先生成关键问题阅读报告</h2>
          <p className="mt-2 text-sm text-slate-500">近邻检索使用带页码的研究问题、方法和贡献作为确定性锚点。</p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto bg-slate-50">
      <div className="mx-auto max-w-6xl space-y-4 p-6 pb-16">
        <header className="flex flex-wrap items-start justify-between gap-4 rounded-lg border border-slate-200 bg-white p-5">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-700">Related Work</div>
            <h1 className="mt-1 text-xl font-semibold text-slate-950">近邻论文 / 相关工作</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
              以论文标题、摘要与报告锚点提取的关键词为主检索；arXiv 与 Elasticsearch 是主通道，其余学术元数据作为补充。不判断任何论文主张为真、假、支持或反驳。
            </p>
          </div>
          <Button onClick={() => void run(Boolean(snapshot))} disabled={loading || initializing}>
            {loading || initializing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : snapshot ? <RefreshCw className="mr-2 h-4 w-4" /> : <Network className="mr-2 h-4 w-4" />}
            {snapshot ? '刷新近邻' : '查找近邻'}
          </Button>
        </header>

        {snapshot && (
          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <span className="inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                当前使用：{backendLabel(snapshot.search_backend)}
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
              <span>锚点：{snapshot.anchors.length}</span>
              <span>结果池：{snapshot.neighbors.length}</span>
              <span>arXiv：{snapshot.source_counts?.arxiv || 0}</span>
              <span>Elasticsearch：{snapshot.source_counts?.elasticsearch || 0}</span>
              <span>补充：{snapshot.source_counts?.supplemental || 0}</span>
              <span>{snapshot.cache_hit ? '缓存命中' : '本次生成'}</span>
              <span>{new Date(snapshot.generated_at).toLocaleString('zh-CN', { hour12: false })}</span>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(snapshot.provider_status).map(([name, status]) => {
                const presentation = describeProviderStatus(name, status, snapshot.search_backend)
                return (
                  <span
                    key={name}
                    title={status.error || status.reason || status.status}
                    className={`rounded-full px-2.5 py-1 text-[11px] ${presentation.className}`}
                  >
                    {presentation.label}：{presentation.detail}
                  </span>
                )
              })}
            </div>
            <p className="mt-3 text-[11px] leading-5 text-slate-500">
              外部学术来源默认通过代理访问；代理不可用时停止外部请求，不会静默直连。Elasticsearch 连接由用户配置的本机或局域网实例且不经过学术代理；内置论文索引只作为明确披露的回退。
            </p>
            {snapshot.search_keywords?.length ? (
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-[11px] font-medium text-slate-600">关键词检索</span>
                {snapshot.search_keywords.map(keyword => (
                  <code key={keyword} className="rounded bg-emerald-50 px-2 py-1 text-[10px] text-emerald-700">{keyword}</code>
                ))}
              </div>
            ) : null}
            {snapshot.queries?.length ? (
              <details className="mt-2 text-[11px] text-slate-500">
                <summary className="cursor-pointer select-none font-medium">查看组合检索式</summary>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {snapshot.queries.map(query => (
                    <code key={query} className="rounded bg-slate-100 px-2 py-1 text-[10px] text-slate-600">{query}</code>
                  ))}
                </div>
              </details>
            ) : null}
            {snapshot.provider_status.google_scholar?.manual_search_url && (
              <a
                href={snapshot.provider_status.google_scholar.manual_search_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-blue-700 hover:underline"
              >
                通过系统代理在 Scholar 手动搜索当前锚点<ExternalLink className="h-3 w-3" />
              </a>
            )}
          </section>
        )}

        {snapshot?.anchors.length ? (
          <details className="rounded-lg border border-slate-200 bg-white p-4">
            <summary className="cursor-pointer select-none text-sm font-semibold text-slate-900">检索锚点（{snapshot.anchors.length}）</summary>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {snapshot.anchors.map(anchor => (
                <div key={anchor.anchor_id} className="rounded-md border border-slate-200 bg-slate-50 p-3">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                    {anchorLabels[anchor.kind] || anchor.kind} · 第 {anchor.pages.join('、')} 页
                  </div>
                  <p className="mt-1 line-clamp-3 text-xs leading-5 text-slate-700">{anchor.text}</p>
                </div>
              ))}
            </div>
          </details>
        ) : null}

        {snapshot?.neighbors.length ? (
          <section className="space-y-3">
            <PaginationControls
              page={page}
              totalPages={totalPages}
              pageSize={pageSize}
              total={totalNeighbors}
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
            />
            {visibleNeighbors.map(neighbor => {
              const link = neighbor.official_url || neighbor.arxiv_url || neighbor.pdf_url || (neighbor.doi ? `https://doi.org/${neighbor.doi}` : '')
              const retrievedAt = neighbor.provenance.retrieved_at
                ? new Date(neighbor.provenance.retrieved_at)
                : null
              const hasRetrievedAt = Boolean(retrievedAt && !Number.isNaN(retrievedAt.getTime()))
              return (
                <article key={neighbor.canonical_paper_id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm shadow-slate-100">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <span className={`mb-1.5 inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${neighbor.source_role === 'supplemental' ? 'bg-slate-100 text-slate-600' : 'bg-emerald-50 text-emerald-700'}`}>
                        {discoveryChannelLabel(neighbor.discovery_channel)}
                      </span>
                      <h2 className="text-[15px] font-semibold leading-6 text-slate-950">{neighbor.title}</h2>
                      <p className="mt-1 text-xs text-slate-500">
                        {neighbor.authors.slice(0, 5).join('、')}{neighbor.authors.length > 5 ? ' 等' : ''}
                        {neighbor.year ? ` · ${neighbor.year}` : ''}{neighbor.venue ? ` · ${neighbor.venue}` : ''}
                      </p>
                    </div>
                    <span className="shrink-0 rounded-full bg-blue-50 px-2.5 py-1 font-mono text-xs text-blue-700">相关度 {neighbor.relevance_score.toFixed(1)}</span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {neighbor.matched_anchor_ids.map(id => {
                      const anchor = anchors.get(id)
                      return <span key={id} className="rounded bg-slate-100 px-2 py-1 text-[11px] text-slate-600">{anchorLabels[anchor?.kind || ''] || '锚点'} · p.{anchor?.pages.join(',') || '?'}</span>
                    })}
                    {neighbor.overlapping_terms.map(term => <span key={term} className="rounded bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700">{term}</span>)}
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
                    <span>元数据：{providerLabel(neighbor.provenance.provider)}</span>
                    {neighbor.provenance.source_page && <span>来源：本文第 {neighbor.provenance.source_page} 页引文</span>}
                    {hasRetrievedAt && <span>抓取：{retrievedAt?.toLocaleString('zh-CN', { hour12: false })}</span>}
                    {link && <a href={link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium text-blue-700 hover:underline">打开来源<ExternalLink className="h-3 w-3" /></a>}
                  </div>
                  {neighbor.provenance.exact_quote && (
                    <p className="mt-2 border-l-2 border-slate-200 pl-2 text-[11px] leading-5 text-slate-500">
                      本文引文：“{neighbor.provenance.exact_quote}”
                    </p>
                  )}
                </article>
              )
            })}
            <PaginationControls
              page={page}
              totalPages={totalPages}
              pageSize={pageSize}
              total={totalNeighbors}
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
            />
          </section>
        ) : snapshot ? (
          <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
            <SearchX className="mx-auto mb-3 h-8 w-8 text-slate-300" />
            <div className="text-sm font-medium text-slate-700">这次检索暂未返回可展示的近邻论文</div>
            <p className="mx-auto mt-2 max-w-xl text-xs leading-5 text-slate-500">
              这不表示本文没有相关工作。你可以刷新近邻重新检索；未配置的外部来源不会影响上方显示的本地论文索引。
            </p>
          </div>
        ) : !initializing ? (
          <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">点击“查找近邻”，冷检索总 deadline 为 8 秒，单个提供方失败不会触发模型猜测。</div>
        ) : null}
      </div>
    </div>
  )
}
