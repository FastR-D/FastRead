import { useState } from 'react'
import { AlertTriangle, CheckCircle2, ExternalLink, Filter, RefreshCw, SearchCheck, ShieldAlert, ShieldCheck } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { rerun_verification_claim, rerun_verification_task, verify_task_online } from '@/services/note'
import { useTaskStore } from '@/store/taskStore'
import type { ClaimVerification, NoteInsights, Task, TaskStatus, VerificationClaim } from '@/store/taskStore'

interface VerificationReportViewProps {
  task: Task | null
}

type VerificationSnapshot = {
  status?: TaskStatus
  message?: string
  error?: Task['error']
  result?: { insights?: NoteInsights }
  insights?: NoteInsights
}

const verdictTone: Record<string, string> = {
  supported: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  refuted: 'border-red-200 bg-red-50 text-red-700',
  mixed: 'border-amber-200 bg-amber-50 text-amber-700',
  insufficient: 'border-slate-200 bg-slate-50 text-slate-600',
  data_void: 'border-orange-200 bg-orange-50 text-orange-700',
  source_risk: 'border-red-200 bg-red-50 text-red-700',
}

const verdictIcon: Record<string, typeof CheckCircle2> = {
  supported: CheckCircle2,
  refuted: ShieldAlert,
  source_risk: ShieldAlert,
  mixed: AlertTriangle,
  insufficient: AlertTriangle,
  data_void: AlertTriangle,
}

const tierTone: Record<string, string> = {
  A: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  B: 'border-blue-200 bg-blue-50 text-blue-700',
  C: 'border-amber-200 bg-amber-50 text-amber-700',
  D: 'border-slate-200 bg-slate-50 text-slate-500',
  blocked: 'border-red-200 bg-red-50 text-red-700',
}

const stanceTone: Record<string, string> = {
  support: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  refute: 'border-red-200 bg-red-50 text-red-700',
  context: 'border-slate-200 bg-slate-50 text-slate-600',
}

const verdictLabel: Record<string, string> = {
  supported: '支持',
  refuted: '反证',
  mixed: '混合',
  insufficient: '证据不足',
  data_void: '数据空缺',
  source_risk: '信源风险',
}

const stanceLabel: Record<string, string> = {
  support: '支持',
  refute: '反驳',
  context: '背景',
}

const fetchStatusLabel: Record<string, string> = {
  ok: '已抓取',
  pdf_ok: 'PDF 已解析',
  empty: '正文为空',
  fetched: '已抓取',
  skipped: '已跳过',
  failed: '抓取失败',
  not_fetched: '未抓取',
}

const activeVerificationStatuses: TaskStatus[] = [
  'PENDING',
  'EXTRACTING_CLAIMS',
  'SEARCHING_WEB',
  'FETCHING_SOURCES',
  'EVALUATING_EVIDENCE',
  'WRITING_REPORT',
  'RUNNING',
]

const statusLabel: Record<string, string> = {
  PENDING: '排队中',
  EXTRACTING_CLAIMS: '解析输入',
  SEARCHING_WEB: '联网检索',
  FETCHING_SOURCES: '抓取信源',
  EVALUATING_EVIDENCE: '评估证据',
  WRITING_REPORT: '生成报告',
  RUNNING: '运行中',
}

const progressByStatus: Record<string, number> = {
  PENDING: 8,
  EXTRACTING_CLAIMS: 18,
  SEARCHING_WEB: 38,
  FETCHING_SOURCES: 58,
  EVALUATING_EVIDENCE: 78,
  WRITING_REPORT: 92,
  RUNNING: 45,
}

function isActiveVerificationStatus(status?: string) {
  return activeVerificationStatuses.includes(status as TaskStatus)
}

function getVerification(task: Task | null): ClaimVerification | undefined {
  return task?.insights?.verification || (task as any)?.result?.verification_result
}

function claimMergeKey(claim: VerificationClaim) {
  return claim.online?.claim_id || claim.claim
}

function mergeInsights(
  currentInsights: NoteInsights | undefined,
  currentVerification: ClaimVerification | undefined,
  incomingInsights: NoteInsights
): NoteInsights {
  const incomingVerification = incomingInsights.verification
  if (!currentVerification || !incomingVerification) {
    return incomingInsights
  }

  const currentClaims = currentVerification.claims || []
  const incomingClaims = incomingVerification.claims || []
  if (!currentClaims.length || incomingClaims.length >= currentClaims.length) {
    return incomingInsights
  }

  const incomingByKey = new Map(incomingClaims.map(claim => [claimMergeKey(claim), claim]))
  return {
    ...(currentInsights || {}),
    ...incomingInsights,
    verification: {
      ...currentVerification,
      ...incomingVerification,
      claims: currentClaims.map(claim => incomingByKey.get(claimMergeKey(claim)) || claim),
      claim_counts: incomingVerification.claim_counts || currentVerification.claim_counts,
      overall: incomingVerification.overall || currentVerification.overall,
    },
  }
}

function shortId(id?: string) {
  if (!id) return '—'
  return id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id
}

function formatTimestamp(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function InputSourceAudit({ audit }: { audit?: Record<string, any> }) {
  const inputSource = audit?.input_source
  if (!inputSource || !Object.keys(inputSource).length) return null

  const requestedUrl = String(inputSource.requested_url || '')
  const fetchedUrl = String(inputSource.fetched_url || requestedUrl)
  const canonicalUrl = String(inputSource.canonical_url || '')
  const redirectChain = Array.isArray(inputSource.redirect_chain)
    ? inputSource.redirect_chain.map((item: any) => String(item?.url || item || '')).filter(Boolean)
    : []
  const fetchStatus = String(inputSource.fetch_status || 'not_fetched')
  const statusText = fetchStatusLabel[fetchStatus] || fetchStatus
  const textChars = Number(inputSource.text_chars)
  const statusTone =
    fetchStatus === 'ok' || fetchStatus === 'pdf_ok' || fetchStatus === 'fetched'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
      : fetchStatus === 'failed'
        ? 'border-red-200 bg-red-50 text-red-700'
        : 'border-amber-200 bg-amber-50 text-amber-700'
  if (!requestedUrl && !fetchedUrl && !inputSource.error) return null

  return (
    <div className="border-b border-slate-100 px-5 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">输入源</span>
        <Badge variant="outline" className={`h-5 px-1.5 text-[10px] ${statusTone}`}>
          {statusText}
        </Badge>
        {inputSource.source_type && (
          <Badge variant="outline" className="h-5 border-slate-200 px-1.5 font-mono text-[10px] font-normal text-slate-500">
            {inputSource.source_type}
          </Badge>
        )}
        <span className="font-mono text-[10px] text-slate-400">
          {Number.isFinite(textChars) ? textChars.toLocaleString() : '0'} chars
        </span>
        {inputSource.retrieved_at && (
          <span className="font-mono text-[10px] text-slate-400">
            {formatTimestamp(String(inputSource.retrieved_at))}
          </span>
        )}
      </div>
      <div className="mt-2 min-w-0 space-y-1 font-mono text-[10px] leading-5 text-slate-500">
        {requestedUrl && (
          <div className="flex min-w-0 gap-2">
            <span className="w-16 shrink-0 text-slate-400">request</span>
            <a href={requestedUrl} target="_blank" rel="noopener noreferrer" title={requestedUrl} className="truncate text-slate-700 hover:text-blue-700">
              {requestedUrl}
            </a>
          </div>
        )}
        {fetchedUrl && fetchedUrl !== requestedUrl && (
          <div className="flex min-w-0 gap-2">
            <span className="w-16 shrink-0 text-slate-400">fetched</span>
            <a href={fetchedUrl} target="_blank" rel="noopener noreferrer" title={fetchedUrl} className="truncate text-slate-700 hover:text-blue-700">
              {fetchedUrl}
            </a>
          </div>
        )}
        {canonicalUrl && canonicalUrl !== fetchedUrl && (
          <div className="flex min-w-0 gap-2">
            <span className="w-16 shrink-0 text-slate-400">canonical</span>
            <span title={canonicalUrl} className="truncate text-amber-700">{canonicalUrl}</span>
          </div>
        )}
        {inputSource.title && (
          <div className="flex min-w-0 gap-2">
            <span className="w-16 shrink-0 text-slate-400">title</span>
            <span className="truncate text-slate-700">{inputSource.title}</span>
          </div>
        )}
        {(inputSource.publisher || inputSource.author || inputSource.published_at) && (
          <div className="flex min-w-0 gap-2">
            <span className="w-16 shrink-0 text-slate-400">identity</span>
            <span className="truncate">
              {[inputSource.publisher, inputSource.author, inputSource.published_at].filter(Boolean).join(' · ')}
            </span>
          </div>
        )}
        {redirectChain.length > 1 && (
          <div className="flex min-w-0 gap-2">
            <span className="w-16 shrink-0 text-slate-400">redirect</span>
            <span className="min-w-0 break-all">{redirectChain.join(' -> ')}</span>
          </div>
        )}
        {inputSource.error && (
          <div className="flex min-w-0 gap-2 text-red-700">
            <span className="w-16 shrink-0 text-red-400">error</span>
            <span className="truncate">{inputSource.error}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function SourceList({ claim }: { claim: VerificationClaim }) {
  const sources = claim.online?.sources || []
  if (!sources.length) {
    return <div className="text-xs text-slate-400">没有抓取到可展示来源。</div>
  }
  const visibleSources = sources.slice(0, 6)

  return (
    <div>
      <div className="mb-2 font-mono text-[10px] text-slate-400">
        共 {sources.length} 个来源，展示前 {visibleSources.length} 个
      </div>
      <div className="grid gap-2 md:grid-cols-2">
      {visibleSources.map((source, index) => (
        <a
          key={`${source.url}-${index}`}
          href={source.url}
          target="_blank"
          rel="noreferrer"
          className="rounded-sm border border-slate-200 bg-white p-2.5 transition hover:border-slate-300"
        >
          <div className="flex items-center gap-1.5">
            <Badge variant="outline" className={`h-5 px-1.5 text-[10px] ${tierTone[source.trust_tier || (source.trusted ? 'B' : 'D')]}`}>
              {source.trust_tier || (source.trusted ? 'B' : 'D')}
            </Badge>
            <Badge variant="outline" className="h-5 border-slate-200 px-1.5 font-mono text-[10px] font-normal text-slate-500">
              {fetchStatusLabel[source.fetch_status || 'not_fetched'] || source.fetch_status || '未抓取'}
            </Badge>
            <ExternalLink className="ml-auto h-3 w-3 text-slate-300" />
          </div>
          <div className="mt-1.5 line-clamp-2 text-xs font-medium leading-5 text-slate-800">
            {source.title || source.domain || source.url}
          </div>
          <div className="mt-1 truncate font-mono text-[10px] text-slate-400">{source.domain}</div>
          <div className="mt-1 flex flex-wrap gap-1 font-mono text-[10px] text-slate-400">
            <span>{shortId(source.source_id)}</span>
            {source.independence_group && <span>grp {shortId(source.independence_group)}</span>}
            {source.content_hash && <span>hash {shortId(source.content_hash)}</span>}
          </div>
          {source.canonical_url && source.canonical_url !== source.url && (
            <div className="mt-1 truncate font-mono text-[10px] text-amber-600">
              canonical {source.canonical_url}
            </div>
          )}
          {!!source.risk_flags?.length && (
            <div className="mt-1 flex flex-wrap gap-1">
              {source.risk_flags.slice(0, 3).map(flag => (
                <span key={flag} className="rounded-sm border border-amber-200 bg-amber-50 px-1 py-0.5 text-[10px] text-amber-700">
                  {flag}
                </span>
              ))}
            </div>
          )}
          {source.retrieved_at && (
            <div className="mt-1.5 font-mono text-[10px] text-slate-400">
              访问 {formatTimestamp(source.retrieved_at)}
            </div>
          )}
        </a>
      ))}
      </div>
    </div>
  )
}

function EvidenceList({ claim }: { claim: VerificationClaim }) {
  const evidence = claim.online?.evidence || []
  if (!evidence.length) {
    return <div className="text-xs text-slate-400">没有正文证据片段；该主张不能被判为已支持。</div>
  }
  const visibleEvidence = evidence.slice(0, 5)

  return (
    <div className="space-y-2">
      <div className="font-mono text-[10px] text-slate-400">
        共 {evidence.length} 条证据，展示前 {visibleEvidence.length} 条
      </div>
      {visibleEvidence.map((item, index) => (
        <div key={`${item.source_url}-${index}`} className="rounded-sm border border-slate-200 bg-slate-50/60 p-2.5">
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            <Badge variant="outline" className={`h-5 px-1.5 text-[10px] ${stanceTone[item.stance] || 'border-slate-200 bg-slate-50 text-slate-600'}`}>
              {stanceLabel[item.stance] || item.stance}
            </Badge>
            {item.exact_value && (
              <Badge variant="outline" className="h-5 border-slate-200 px-1.5 font-mono text-[10px] font-normal text-slate-700">
                {item.exact_value}{item.unit ? ` ${item.unit}` : ''}
              </Badge>
            )}
            <span className="ml-auto font-mono text-[10px] text-slate-400">
              {shortId(item.evidence_id)} · 置信度 {item.confidence ?? 0}
            </span>
          </div>
          <p className="text-xs leading-5 text-slate-700">{item.passage}</p>
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] text-slate-400">
            {item.page_offsets?.page_start && (
              <span>
                页 {item.page_offsets.page_start}
                {item.page_offsets.page_end && item.page_offsets.page_end !== item.page_offsets.page_start
                  ? `-${item.page_offsets.page_end}`
                  : ''}
              </span>
            )}
            {item.page_offsets?.start !== undefined && item.page_offsets?.end !== undefined && (
              <span>chars {item.page_offsets.start}-{item.page_offsets.end}</span>
            )}
            {item.extraction_method && <span>{item.extraction_method}</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

function ClaimReport({
  claim,
  index,
  canRerun,
  rerunning,
  rerunDisabled,
  onRerun,
}: {
  claim: VerificationClaim
  index: number
  canRerun: boolean
  rerunning: boolean
  rerunDisabled: boolean
  onRerun: (claimId: string) => void
}) {
  const status = claim.online?.status || claim.machine_verdict || claim.verdict
  const Icon = verdictIcon[status] || AlertTriangle
  const metrics = claim.online?.metrics
  const audit = claim.online?.audit || {}
  const cacheAudit = audit.cache
  const geoComparison = audit.geo_comparison
  const claimId = claim.online?.claim_id

  return (
    <article className="rounded-md border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-2.5">
        <span className="font-mono text-[11px] font-semibold tabular-nums text-slate-400">
          #{String(index + 1).padStart(2, '0')}
        </span>
        <Badge variant="outline" className={`h-5 px-1.5 text-[10px] ${verdictTone[status] || 'border-slate-200 bg-slate-50 text-slate-600'}`}>
          {verdictLabel[status] || status}
        </Badge>
        <Badge variant="outline" className="h-5 border-slate-200 px-1.5 text-[10px] font-normal text-slate-500">
          {claim.type_label || claim.type}
        </Badge>
        <span className="ml-auto font-mono text-[10px] text-slate-400">
          置信度 {claim.online?.confidence ?? claim.confidence ?? 0}
        </span>
        {canRerun && claimId && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label={`重新核实第 ${index + 1} 条主张`}
            disabled={rerunDisabled}
            onClick={() => onRerun(claimId)}
            className="h-7 px-2 text-[11px] text-slate-500 hover:bg-slate-50 hover:text-slate-800"
          >
            <RefreshCw className={`mr-1 h-3.5 w-3.5 ${rerunning ? 'animate-spin' : ''}`} />
            {rerunning ? '重跑中' : '重跑'}
          </Button>
        )}
      </div>

      <div className="px-4 py-3">
        <div className="flex gap-2">
          <Icon className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
          <div className="min-w-0">
            <h3 className="text-sm font-semibold leading-6 text-slate-900">{claim.claim}</h3>
            <p className="mt-1 text-xs leading-5 text-slate-500">{claim.online?.reason || claim.reason}</p>
          </div>
        </div>

        {!!claim.online?.risk_flags?.length && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {claim.online.risk_flags.map(flag => (
              <span key={flag} className="inline-flex items-center rounded-sm border border-red-200 bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-700">
                {flag}
              </span>
            ))}
          </div>
        )}

        {metrics && (
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-slate-400">
            {metrics.coverage !== undefined && <span>覆盖 {metrics.coverage}</span>}
            {metrics.trusted_count !== undefined && <span>可信源 {metrics.trusted_count}</span>}
            {metrics.independent_authoritative_sources !== undefined && <span>独立权威 {metrics.independent_authoritative_sources}</span>}
          </div>
        )}

        {(cacheAudit || geoComparison) && (
          <div className="mt-3 grid gap-2 border-y border-slate-100 py-2 md:grid-cols-2">
            {cacheAudit && (
              <div className="font-mono text-[10px] leading-5 text-slate-500">
                <span className="font-semibold text-slate-600">cache</span>
                <span className="ml-2">SERP {cacheAudit.serp?.hit ? 'hit' : 'miss'}</span>
                <span className="ml-2">snap {cacheAudit.snapshots?.filter((item: any) => item.hit).length ?? 0}/{cacheAudit.snapshots?.length ?? 0}</span>
                <span className="ml-2">ev {cacheAudit.evidence?.filter((item: any) => item.hit).length ?? 0}/{cacheAudit.evidence?.length ?? 0}</span>
              </div>
            )}
            {geoComparison && (
              <div className="font-mono text-[10px] leading-5 text-slate-500">
                <span className="font-semibold text-slate-600">geo</span>
                {Object.entries(geoComparison).map(([bucket, item]: [string, any]) => (
                  <span key={bucket} className="ml-2">
                    {bucket}:{item?.dominant_stance || 'none'}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(300px,0.8fr)]">
          <div>
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">正文证据</div>
            <EvidenceList claim={claim} />
          </div>
          <div>
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">来源矩阵</div>
            <SourceList claim={claim} />
          </div>
        </div>
      </div>
    </article>
  )
}

export default function VerificationReportView({ task }: VerificationReportViewProps) {
  const verification = getVerification(task)
  const [verifying, setVerifying] = useState(false)
  const [rerunningClaimId, setRerunningClaimId] = useState<string | null>(null)
  const [verdictFilter, setVerdictFilter] = useState('all')
  const [riskFilter, setRiskFilter] = useState('all')
  const [tierFilter, setTierFilter] = useState('all')
  const [domainFilter, setDomainFilter] = useState('all')
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)
  const isVerificationTask = ['text', 'url'].includes(task?.formData?.input_mode || '')
  const taskStatus = task?.status || 'PENDING'
  const taskIsActive = isActiveVerificationStatus(taskStatus)
  const taskFailed = taskStatus === 'FAILED'
  const reportBusy = verifying || Boolean(rerunningClaimId) || taskIsActive

  const applyVerificationSnapshot = (snapshot: VerificationSnapshot) => {
    if (!task?.id) return
    const next: Partial<Omit<Task, 'id' | 'createdAt'>> = {}
    const insights = snapshot.result?.insights || snapshot.insights
    if (insights) next.insights = mergeInsights(task.insights, verification, insights)
    if (snapshot.status) next.status = snapshot.status
    if ('message' in snapshot) next.message = snapshot.message
    if ('error' in snapshot) next.error = snapshot.error
    updateTaskContent(task.id, next)
  }

  const handleVerify = async () => {
    if (!task?.id || reportBusy) return
    setVerifying(true)
    const previousStatus = task.status
    const previousMessage = task.message
    const previousError = task.error
    try {
      const isVerificationTask = ['text', 'url'].includes(task.formData?.input_mode || '')
      if (isVerificationTask) {
        updateTaskContent(task.id, {
          status: 'SEARCHING_WEB',
          message: '重新联网核实中',
          error: undefined,
        })
        const snapshot = await rerun_verification_task(task.id, true) as VerificationSnapshot
        applyVerificationSnapshot(snapshot)
        toast.success('已重试失败阶段')
      } else {
        const res = await verify_task_online({
          task_id: task.id,
          max_claims: 50,
          model_name: task.formData?.model_name,
          provider_id: task.formData?.provider_id,
        }) as { insights?: NoteInsights }
        updateTaskContent(task.id, { insights: res.insights })
        toast.success('联网核实完成')
      }
    }
    catch (error) {
      updateTaskContent(task.id, {
        status: previousStatus,
        message: previousMessage,
        error: previousError,
      })
      const message =
        error && typeof error === 'object' && 'msg' in error
          ? String((error as { msg?: string }).msg)
          : '联网核实失败'
      toast.error(message)
    }
    finally {
      setVerifying(false)
    }
  }

  const handleRerunClaim = async (claimId: string) => {
    if (!task?.id || reportBusy) return
    setRerunningClaimId(claimId)
    const previousStatus = task.status
    const previousMessage = task.message
    const previousError = task.error
    try {
      updateTaskContent(task.id, {
        status: 'SEARCHING_WEB',
        message: '重新核实单条主张中',
        error: undefined,
      })
      const snapshot = await rerun_verification_claim(task.id, claimId) as VerificationSnapshot
      applyVerificationSnapshot(snapshot)
      toast.success('该主张已重新核实')
    }
    catch (error) {
      updateTaskContent(task.id, {
        status: previousStatus,
        message: previousMessage,
        error: previousError,
      })
      const message =
        error && typeof error === 'object' && 'msg' in error
          ? String((error as { msg?: string }).msg)
          : '单条主张重跑失败'
      toast.error(message)
    }
    finally {
      setRerunningClaimId(null)
    }
  }

  if (!verification) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-50/40 px-6 text-center">
        <div className="max-w-sm">
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-sm border border-slate-200 bg-white text-slate-400">
            <SearchCheck className="h-4 w-4" />
          </div>
          <p className="mt-3 text-sm font-semibold text-slate-800">等待联网核实任务</p>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            提交 URL 或文本后，会在这里显示证据矩阵与逐条判定。
          </p>
        </div>
      </div>
    )
  }

  const overall = verification.overall
  const counts = verification.claim_counts
  const reportAudit = (verification.result?.audit || (verification as any).audit) as Record<string, any> | undefined
  const depth = task?.formData?.verification_depth === 'deep' ? '深度核验' : '标准核验'
  const policy = task?.formData?.source_policy === 'authoritative' ? '权威优先' : '—'
  const progressValue = progressByStatus[taskStatus] ?? 45
  const riskOptions = Array.from(new Set(verification.claims.flatMap(claim => claim.online?.risk_flags || []))).sort()
  const tierOptions = Array.from(new Set(verification.claims.flatMap(claim => (claim.online?.sources || []).map(source => source.trust_tier || (source.trusted ? 'B' : 'D'))))).sort()
  const domainOptions = Array.from(new Set(verification.claims.flatMap(claim => (claim.online?.sources || []).map(source => source.domain).filter(Boolean)))).sort()
  const filteredClaims = verification.claims.filter(claim => {
    const status = claim.online?.status || claim.machine_verdict || claim.verdict
    const risks = claim.online?.risk_flags || []
    const sources = claim.online?.sources || []
    if (verdictFilter !== 'all' && status !== verdictFilter) return false
    if (riskFilter !== 'all' && !risks.includes(riskFilter)) return false
    if (tierFilter !== 'all' && !sources.some(source => (source.trust_tier || (source.trusted ? 'B' : 'D')) === tierFilter)) return false
    if (domainFilter !== 'all' && !sources.some(source => source.domain === domainFilter)) return false
    return true
  })

  return (
    <ScrollArea className="h-full bg-slate-50/40">
      <div className="mx-auto max-w-7xl px-5 py-5">
        {/* 报告头 */}
        <div className="rounded-md border border-slate-200 bg-white">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-slate-700" />
                <h2 className="text-base font-semibold text-slate-900">联网核实报告</h2>
                <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
                  {overall?.status ? verdictLabel[overall.status] || overall.status : '等待核实'}
                </Badge>
                <span className="inline-flex items-center rounded-sm border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-500">
                  {depth}
                </span>
                <span className="inline-flex items-center rounded-sm border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-500">
                  {policy}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] text-slate-400">
                <span>会话 {shortId(task?.id)}</span>
                {task?.createdAt && <span>创建 {formatTimestamp(task.createdAt)}</span>}
                <span>主张 {counts?.total ?? verification.claims.length}</span>
              </div>
              {overall?.summary && (
                <p className="mt-2 max-w-3xl text-xs leading-5 text-slate-600">{overall.summary}</p>
              )}
              {overall?.note && (
                <p className="mt-1 max-w-3xl text-[11px] leading-5 text-slate-400">{overall.note}</p>
              )}
            </div>
            <Button onClick={handleVerify} disabled={!task?.id || reportBusy} variant="outline" size="sm" className="h-8">
              <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${reportBusy ? 'animate-spin' : ''}`} />
              {reportBusy ? '核实中' : verification.external_check ? '重试联网核实' : '开始联网核实'}
            </Button>
          </div>

          {taskIsActive && (
            <div className="border-b border-slate-100 px-5 py-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <RefreshCw className="h-3.5 w-3.5 animate-spin text-blue-600" />
                  <span className="text-xs font-medium text-slate-800">
                    {task?.message || statusLabel[taskStatus] || '联网核实中'}
                  </span>
                </div>
                <span className="font-mono text-[10px] text-slate-400">
                  {statusLabel[taskStatus] || taskStatus}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-sm bg-slate-100">
                <div
                  className="h-full rounded-sm bg-blue-600 transition-all duration-500"
                  style={{ width: `${progressValue}%` }}
                />
              </div>
            </div>
          )}

          {taskFailed && (
            <div className="border-b border-red-100 bg-red-50 px-5 py-3">
              <div className="flex items-start gap-2">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600" />
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-red-800">本次重跑失败，已保留上次报告</div>
                  <div className="mt-0.5 text-[11px] leading-5 text-red-700">
                    {task?.error?.message || task?.message || '请检查后台日志或稍后重试。'}
                  </div>
                </div>
              </div>
            </div>
          )}

          <InputSourceAudit audit={reportAudit} />

          {/* 统计行 */}
          <div className="grid grid-cols-2 divide-x divide-slate-100 sm:grid-cols-5">
            <StatCell label="主张" value={counts?.total ?? verification.claims.length} tone="text-slate-900" />
            <StatCell label="已联网" value={counts?.online_checked ?? 0} tone="text-slate-900" />
            <StatCell label="支持" value={counts?.online_supported ?? 0} tone="text-emerald-700" />
            <StatCell label="反证" value={counts?.online_refuted ?? 0} tone="text-red-700" />
            <StatCell label="风险旗标" value={verification.risk_flags?.length ?? 0} tone="text-amber-700" />
          </div>
        </div>

        {/* 逐条主张 */}
        <div className="mt-4 space-y-3">
          <div className="rounded-md border border-slate-200 bg-white p-3">
            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              <Filter className="h-3.5 w-3.5" />
              报告筛选
            </div>
            <div className="grid gap-2 md:grid-cols-4">
              <FilterSelect label="判定" value={verdictFilter} onChange={setVerdictFilter} options={[
                ['all', '全部判定'],
                ['supported', '支持'],
                ['refuted', '反证'],
                ['mixed', '混合'],
                ['insufficient', '证据不足'],
                ['data_void', '数据空缺'],
                ['source_risk', '信源风险'],
              ]} />
              <FilterSelect label="风险" value={riskFilter} onChange={setRiskFilter} options={[
                ['all', '全部风险'],
                ...riskOptions.map(flag => [flag, flag] as [string, string]),
              ]} />
              <FilterSelect label="等级" value={tierFilter} onChange={setTierFilter} options={[
                ['all', '全部等级'],
                ...tierOptions.map(tier => [tier, `Tier ${tier}`] as [string, string]),
              ]} />
              <FilterSelect label="域名" value={domainFilter} onChange={setDomainFilter} options={[
                ['all', '全部域名'],
                ...domainOptions.map(domain => [domain, domain] as [string, string]),
              ]} />
            </div>
          </div>

          <div className="flex items-center justify-between">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              逐条主张判定
            </h3>
            <span className="font-mono text-[10px] text-slate-400">
              {filteredClaims.length}/{verification.claims.length} claims
            </span>
          </div>
          {filteredClaims.map((claim, index) => (
            <ClaimReport
              key={`${claim.claim}-${index}`}
              claim={claim}
              index={index}
              canRerun={isVerificationTask}
              rerunning={rerunningClaimId === claim.online?.claim_id}
              rerunDisabled={reportBusy}
              onRerun={handleRerunClaim}
            />
          ))}
          {!filteredClaims.length && (
            <div className="rounded-md border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-xs text-slate-400">
              当前筛选条件下没有匹配主张。
            </div>
          )}
        </div>
      </div>
    </ScrollArea>
  )
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: Array<[string, string]>
  onChange: (value: string) => void
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] font-medium text-slate-400">{label}</span>
      <select
        value={value}
        onChange={event => onChange(event.target.value)}
        className="h-8 w-full rounded-sm border border-slate-200 bg-white px-2 text-xs text-slate-700 outline-none transition focus:border-slate-400"
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  )
}

function StatCell({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="px-4 py-3">
      <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1 font-mono text-xl font-semibold tabular-nums ${tone}`}>{value}</div>
    </div>
  )
}
