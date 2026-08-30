import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, BrainCircuit, ChevronLeft, ChevronRight, ExternalLink, Loader2, Network, RefreshCw, SearchX } from 'lucide-react'
import toast from 'react-hot-toast'
import type { Task } from '@/store/taskStore'
import {
  generateRelatedWork,
  getRelatedWork,
  getSmartNeighborSelection,
  startSmartNeighborSelection,
  type RelatedWorkProviderStatus,
  type RelatedWorkSnapshot,
  type SmartNeighborSelection,
} from '@/services/relatedWork'
import { Button } from '@/components/ui/button'
import { useModelStore } from '@/store/modelStore'

const pageSizeOptions = [10, 20, 50, 100]

const anchorLabels: Record<string, string> = {
  research_question: '研究问题',
  method: '方法',
  contribution: '贡献',
  fallback: '标题 / 摘要',
}

const smartRoleLabels: Record<string, string> = {
  direct_competitor: '直接竞争 / 创新威胁',
  same_problem_different_method: '同一问题 · 不同方法',
  same_method_different_problem: '同一方法 · 不同任务',
  evaluation_or_control_neighbor: '评测 / 数据 / 控制近邻',
  background: '重要背景',
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
  if (name === 'paper_bibliography' && diagnostic === 'no_related_work_citations') {
    return { label, detail: '已检查正文 · 未抽取到参考文献题录', className: 'bg-sky-50 text-sky-700' }
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
  const { modelList, loadEnabledModels } = useModelStore()
  const [snapshot, setSnapshot] = useState<RelatedWorkSnapshot | null>(null)
  const [smartSelection, setSmartSelection] = useState<SmartNeighborSelection | null>(null)
  const [loading, setLoading] = useState(false)
  const [smartLoading, setSmartLoading] = useState(false)
  const [initializing, setInitializing] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [selectedModelKey, setSelectedModelKey] = useState('')

  useEffect(() => {
    void loadEnabledModels()
  }, [loadEnabledModels])

  useEffect(() => {
    if (!modelList.length) {
      setSelectedModelKey('')
      return
    }
    const keys = modelList.map(model => `${model.provider_id}:${model.model_name}`)
    if (!keys.includes(selectedModelKey)) setSelectedModelKey(keys[0])
  }, [modelList, selectedModelKey])

  useEffect(() => {
    setSnapshot(null)
    setSmartSelection(null)
    if (!task) return
    let cancelled = false
    setInitializing(true)
    getRelatedWork(task.id)
      .then(result => { if (!cancelled) setSnapshot(result) })
      .catch(() => undefined)
      .finally(() => { if (!cancelled) setInitializing(false) })
    getSmartNeighborSelection(task.id)
      .then(result => { if (!cancelled) setSmartSelection(result) })
      .catch(() => undefined)
    return () => { cancelled = true }
  }, [task])

  useEffect(() => {
    if (!task || !smartSelection || !['pending', 'running'].includes(smartSelection.status)) return
    let cancelled = false
    const timer = window.setTimeout(() => {
      getSmartNeighborSelection(task.id)
        .then(result => {
          if (cancelled || !result) return
          setSmartSelection(result)
          if (result.status === 'completed') toast.success('AI 智能精选已完成')
          if (result.status === 'failed') toast.error('AI 智能精选失败；完整关键词近邻仍可正常使用')
        })
        .catch(() => undefined)
    }, 1400)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [smartSelection, task])

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
  const smartNeighbors = useMemo(() => {
    const neighbors = new Map((snapshot?.neighbors || []).map(neighbor => [neighbor.canonical_paper_id, neighbor]))
    return (smartSelection?.selections || []).flatMap(selection => {
      const neighbor = neighbors.get(selection.candidate_id)
      return neighbor ? [{ selection, neighbor }] : []
    })
  }, [smartSelection?.selections, snapshot?.neighbors])
  const selectedModel = modelList.find(model => `${model.provider_id}:${model.model_name}` === selectedModelKey)

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
      const nextSnapshot = await generateRelatedWork(task.id, { force, limit: 120 })
      setSnapshot(nextSnapshot)
      setSmartSelection(await getSmartNeighborSelection(task.id).catch(() => null))
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

  const runSmartSelection = async (force = false) => {
    if (!task || !snapshot) return
    if (!selectedModel) {
      toast.error('请先在设置中启用一个模型')
      return
    }
    setSmartLoading(true)
    try {
      const job = await startSmartNeighborSelection(task.id, {
        provider_id: selectedModel.provider_id,
        model_name: selectedModel.model_name,
        force,
        selection_limit: 16,
      })
      setSmartSelection(job)
      if (job.status === 'completed') toast.success('已载入缓存的 AI 智能精选')
      else toast.success('AI 智能精选已在后台开始，完整关键词结果可继续浏览')
    }
    catch (error) {
      console.error('启动 AI 智能精选失败', error)
      toast.error('无法启动 AI 智能精选；完整关键词近邻不受影响')
    }
    finally {
      setSmartLoading(false)
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

        {snapshot && (
          <section data-testid="smart-neighbor-section" className="rounded-lg border border-indigo-200 bg-gradient-to-br from-indigo-50 via-white to-violet-50 p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-2xl">
                <div className="flex items-center gap-2 text-sm font-semibold text-indigo-950">
                  <BrainCircuit className="h-4 w-4" />AI 智能精选
                </div>
                <p className="mt-2 text-xs leading-5 text-indigo-900/70">
                  模型只在代码校验后的封闭候选池中比较研究问题、方法、证据与创新威胁；它不能新增论文，也不会隐藏下面的完整关键词近邻。
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  aria-label="智能精选模型"
                  className="max-w-56 rounded-md border border-indigo-200 bg-white px-2 py-2 text-xs text-slate-700"
                  value={selectedModelKey}
                  onChange={event => setSelectedModelKey(event.target.value)}
                  disabled={smartLoading || smartSelection?.status === 'pending' || smartSelection?.status === 'running'}
                >
                  {!modelList.length && <option value="">请先配置模型</option>}
                  {modelList.map(model => (
                    <option key={`${model.provider_id}:${model.model_name}`} value={`${model.provider_id}:${model.model_name}`}>
                      {model.model_name}
                    </option>
                  ))}
                </select>
                <Button
                  variant="outline"
                  onClick={() => void runSmartSelection(smartSelection?.status === 'completed' || smartSelection?.status === 'failed')}
                  disabled={smartLoading || !modelList.length || smartSelection?.status === 'pending' || smartSelection?.status === 'running'}
                >
                  {smartLoading || smartSelection?.status === 'pending' || smartSelection?.status === 'running'
                    ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    : <BrainCircuit className="mr-2 h-4 w-4" />}
                  {smartSelection?.status === 'completed' ? '重新精选' : '生成智能精选'}
                </Button>
              </div>
            </div>

            {smartSelection?.status === 'failed' && (
              <div className="mt-4 flex gap-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  <div className="font-semibold">模型精选未完成，已明确保留关键词结果</div>
                  <div>{smartSelection.failure_reason || 'model_failed'}：{smartSelection.error || '模型没有返回可校验结果'}</div>
                </div>
              </div>
            )}

            {smartSelection && ['pending', 'running'].includes(smartSelection.status) && (
              <div className="mt-4 rounded-md border border-indigo-100 bg-white/80 p-3 text-xs text-indigo-800">
                后台正在比较 {smartSelection.candidate_count} 篇候选；你可以继续翻阅下方关键词近邻。
              </div>
            )}

            {smartSelection?.status === 'completed' && (
              <>
                <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-indigo-800/80">
                  <span className="rounded-full bg-white px-2.5 py-1">模型：{smartSelection.model_name}</span>
                  <span className="rounded-full bg-white px-2.5 py-1">候选：{smartSelection.candidate_count} 篇</span>
                  <span className="rounded-full bg-white px-2.5 py-1">精选：{smartSelection.selected_count} 篇</span>
                  {smartSelection.metadata.context_policy && (
                    <span className="rounded-full bg-white px-2.5 py-1">
                      源论文正文：{smartSelection.metadata.context_policy.included_page_count}/{smartSelection.metadata.context_policy.source_page_count} 页 · {smartSelection.metadata.context_policy.context_characters.toLocaleString()} 字
                    </span>
                  )}
                  {smartSelection.metadata.code_filter && (
                    <span className="rounded-full bg-white px-2.5 py-1">
                      代码门槛 ≥ {smartSelection.metadata.code_filter.minimum_combined_score} · 背景最多 {smartSelection.metadata.code_filter.maximum_background_items} 篇
                    </span>
                  )}
                  <span className="rounded-full bg-white px-2.5 py-1">{smartSelection.prompt_version}</span>
                </div>
                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  {smartNeighbors.map(({ selection, neighbor }) => {
                    const link = neighbor.official_url || neighbor.arxiv_url || neighbor.pdf_url || (neighbor.doi ? `https://doi.org/${neighbor.doi}` : '')
                    return (
                      <article key={selection.candidate_id} className="rounded-lg border border-indigo-100 bg-white p-4 shadow-sm">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <span className="rounded-full bg-indigo-50 px-2 py-1 text-[10px] font-semibold text-indigo-700">{smartRoleLabels[selection.role]}</span>
                            <h2 className="mt-2 text-sm font-semibold leading-6 text-slate-950">{neighbor.title}</h2>
                            <p className="mt-1 text-[11px] text-slate-500">{neighbor.year || '年份未知'}{neighbor.venue ? ` · ${neighbor.venue}` : ''}</p>
                          </div>
                          <span className="shrink-0 rounded-full bg-indigo-600 px-2.5 py-1 font-mono text-xs text-white">精选 {selection.combined_score.toFixed(1)}</span>
                        </div>
                        <p className="mt-3 text-xs leading-5 text-slate-700">{selection.reason}</p>
                        {selection.contrast && <p className="mt-2 border-l-2 border-indigo-100 pl-2 text-[11px] leading-5 text-slate-500">差异 / 待核验：{selection.contrast}</p>}
                        <div className="mt-3 flex flex-wrap gap-1.5 text-[10px] text-slate-600">
                          <span className="rounded bg-slate-100 px-2 py-1">问题 {selection.scores.research_problem}/3</span>
                          <span className="rounded bg-slate-100 px-2 py-1">方法 {selection.scores.method}/3</span>
                          <span className="rounded bg-slate-100 px-2 py-1">证据 {selection.scores.evidence}/3</span>
                          <span className="rounded bg-slate-100 px-2 py-1">创新威胁 {selection.scores.novelty_threat}/3</span>
                          {link && <a href={link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded bg-blue-50 px-2 py-1 font-medium text-blue-700">打开来源<ExternalLink className="h-3 w-3" /></a>}
                        </div>
                      </article>
                    )
                  })}
                </div>
                <p className="mt-4 text-[11px] leading-5 text-indigo-900/60">智能理由基于源论文正文与候选题名/摘要；代码会丢弃低分项并限制背景论文数量，不要求模型凑满名额。候选全文导入前仍属于发现判断，不构成对其主张的验证。</p>
              </>
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
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-slate-900">全部关键词近邻</h2>
                <p className="mt-1 text-xs text-slate-500">完整召回池始终保留，可分页浏览；AI 精选不会删除或遮蔽这些论文。</p>
              </div>
            </div>
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
