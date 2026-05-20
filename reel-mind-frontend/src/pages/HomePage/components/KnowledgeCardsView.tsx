import { useState } from 'react'
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  CheckCircle2,
  ClipboardCheck,
  Layers3,
  Quote,
  ScanSearch,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'
import { toast } from 'react-hot-toast'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { verify_task_online } from '@/services/note'
import { useTaskStore } from '@/store/taskStore'
import type { NoteInsights, VerificationClaim } from '@/store/taskStore'

interface KnowledgeCardsViewProps {
  taskId?: string
  insights?: NoteInsights
}

const scoreLabels = {
  information_density: {
    title: '信息密度',
    icon: Layers3,
    color: 'bg-blue-500',
  },
  credibility: {
    title: '可信度',
    icon: BadgeCheck,
    color: 'bg-emerald-500',
  },
  actionability: {
    title: '可执行性',
    icon: ClipboardCheck,
    color: 'bg-amber-500',
  },
} as const

const cardIcons: Record<string, any> = {
  核心结论: Sparkles,
  概念解释: Layers3,
  操作步骤: ClipboardCheck,
  风险提醒: ShieldAlert,
  行动清单: Activity,
  金句: Quote,
}

function ScoreBlock({ label, score }: { label: keyof typeof scoreLabels; score?: NoteInsights['scores'][keyof NoteInsights['scores']] }) {
  if (!score) return null
  const meta = scoreLabels[label]
  const Icon = meta.icon

  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-neutral-100">
            <Icon className="h-4 w-4 text-neutral-700" />
          </div>
          <div>
            <div className="text-sm font-medium text-neutral-900">{meta.title}</div>
            <div className="text-xs text-neutral-500">{score.level}可信号</div>
          </div>
        </div>
        <div className="text-2xl font-semibold tabular-nums text-neutral-900">{score.score}</div>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-neutral-100">
        <div className={`h-full ${meta.color}`} style={{ width: `${score.score}%` }} />
      </div>
      <p className="mt-3 text-xs leading-5 text-neutral-500">{score.reason}</p>
    </div>
  )
}

const riskLabels = {
  high: '高风险',
  medium: '需核实',
  low: '低风险',
}

const riskClassNames = {
  high: 'border-red-200 bg-red-50 text-red-700',
  medium: 'border-amber-200 bg-amber-50 text-amber-700',
  low: 'border-emerald-200 bg-emerald-50 text-emerald-700',
}

function ClaimItem({ claim }: { claim: VerificationClaim }) {
  const isHighRisk = claim.risk_level === 'high'
  const Icon = isHighRisk ? AlertTriangle : CheckCircle2

  return (
    <article className="rounded-lg border bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className={riskClassNames[claim.risk_level]}>
          {riskLabels[claim.risk_level]}
        </Badge>
        <Badge variant="secondary" className="font-normal">
          {claim.type_label}
        </Badge>
        <Badge variant="outline" className="font-normal">
          {claim.verdict}
        </Badge>
      </div>
      <p className="mt-2 text-sm font-medium leading-6 text-neutral-900">{claim.claim}</p>
      <div className="mt-2 flex gap-2 text-xs leading-5 text-neutral-500">
        <Icon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${isHighRisk ? 'text-red-500' : 'text-neutral-400'}`} />
        <span>{claim.reason}</span>
      </div>
      <p className="mt-2 text-xs leading-5 text-neutral-500">{claim.evidence_hint}</p>
      {claim.online?.checked && claim.online.sources?.length > 0 && (
        <div className="mt-3 rounded-md bg-neutral-50 p-2">
          <div className="mb-1 text-xs font-medium text-neutral-600">联网来源</div>
          <div className="space-y-1">
            {claim.online.sources.slice(0, 3).map((source, index) => (
              <a
                key={`${source.url}-${index}`}
                href={source.url}
                target="_blank"
                rel="noreferrer"
                className="block truncate text-xs text-blue-600 hover:underline"
                title={source.title}
              >
                {source.trusted ? '权威 · ' : ''}{source.title}
              </a>
            ))}
          </div>
        </div>
      )}
    </article>
  )
}

function VerificationPanel({ taskId, insights }: { taskId?: string; insights: NoteInsights }) {
  const verification = insights.verification
  const [verifying, setVerifying] = useState(false)
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)
  const currentTask = useTaskStore(state => state.tasks.find(task => task.id === taskId))
  if (!verification) return null

  const { overall, claim_counts: counts } = verification
  const handleOnlineVerify = async () => {
    if (!taskId || verifying) return
    setVerifying(true)
    try {
      const res = await verify_task_online({
        task_id: taskId,
        max_claims: Math.max(1, verification.claims.length),
        model_name: currentTask?.formData?.model_name,
        provider_id: currentTask?.formData?.provider_id,
      })
      updateTaskContent(taskId, { insights: res.insights })
      const onlineError = res.insights?.verification?.online_error
      if (onlineError) {
        toast.error(onlineError)
      } else {
        toast.success('联网核验完成')
      }
    } catch (error) {
      const message =
        error && typeof error === 'object' && 'msg' in error
          ? String((error as { msg?: string }).msg)
          : '联网核验失败'
      toast.error(message)
    } finally {
      setVerifying(false)
    }
  }

  const statusClass =
    overall.status === '高风险'
      ? 'bg-red-50 text-red-700 border-red-200'
      : overall.status === '需核实'
        ? 'bg-amber-50 text-amber-700 border-amber-200'
        : overall.status === '基本可信'
          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
          : 'bg-neutral-50 text-neutral-600 border-neutral-200'

  return (
    <section className="mt-4 rounded-lg border bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-neutral-100">
            <ScanSearch className="h-5 w-5 text-neutral-700" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold text-neutral-950">可信度核验</h3>
              <Badge variant="outline" className={statusClass}>
                {overall.status}
              </Badge>
              <Badge variant="outline">离线核验</Badge>
            </div>
            <p className="mt-2 text-sm leading-6 text-neutral-600">{overall.summary}</p>
            <p className="mt-1 text-xs leading-5 text-neutral-400">{overall.note}</p>
            {verification.online_error && (
              <p className="mt-1 text-xs leading-5 text-red-400">{verification.online_error}</p>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end gap-2 text-right">
          <div className="text-3xl font-semibold tabular-nums text-neutral-950">{overall.score}</div>
          <div className="text-xs text-neutral-400">核验分</div>
          <Button
            size="sm"
            variant={verification.external_check ? 'outline' : 'default'}
            onClick={handleOnlineVerify}
            disabled={!taskId || verifying}
          >
            <ScanSearch className="mr-1.5 h-4 w-4" />
            {verifying ? '核验中' : verification.external_check ? '重新联网核验' : '联网核验'}
          </Button>
        </div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        <div className="rounded-md bg-neutral-50 px-3 py-2">
          <div className="text-xs text-neutral-400">主张</div>
          <div className="mt-1 text-lg font-semibold text-neutral-900">{counts.total}</div>
        </div>
        <div className="rounded-md bg-amber-50 px-3 py-2">
          <div className="text-xs text-amber-600">需核实</div>
          <div className="mt-1 text-lg font-semibold text-amber-700">{counts.needs_review}</div>
        </div>
        <div className="rounded-md bg-red-50 px-3 py-2">
          <div className="text-xs text-red-600">高风险</div>
          <div className="mt-1 text-lg font-semibold text-red-700">{counts.high_risk}</div>
        </div>
        <div className="rounded-md bg-neutral-50 px-3 py-2">
          <div className="text-xs text-neutral-400">外部检索</div>
          <div className="mt-1 text-lg font-semibold text-neutral-900">
            {verification.external_check ? `${counts.online_checked ?? 0} 条` : '未接入'}
          </div>
        </div>
      </div>

      {verification.claims.length > 0 && (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {verification.claims.map((claim, index) => (
            <ClaimItem key={`${claim.claim}-${index}`} claim={claim} />
          ))}
        </div>
      )}
    </section>
  )
}

export default function KnowledgeCardsView({ taskId, insights }: KnowledgeCardsViewProps) {
  const cards = insights?.cards || []

  if (!insights) {
    return (
      <div className="flex h-full items-center justify-center text-center text-sm text-neutral-400">
        当前笔记还没有知识卡片数据，重新生成后会自动创建。
      </div>
    )
  }

  return (
    <ScrollArea className="h-full bg-neutral-50">
      <div className="mx-auto max-w-6xl px-4 py-5">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-neutral-950">知识卡片</h2>
            <p className="mt-1 text-sm text-neutral-500">
              从笔记、转录与视频元数据中提取的可复用知识单元
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">转录 {insights.summary?.transcript_chars ?? 0} 字</Badge>
            <Badge variant="outline">笔记 {insights.summary?.markdown_chars ?? 0} 字</Badge>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <ScoreBlock label="information_density" score={insights.scores?.information_density} />
          <ScoreBlock label="credibility" score={insights.scores?.credibility} />
          <ScoreBlock label="actionability" score={insights.scores?.actionability} />
        </div>

        <VerificationPanel taskId={taskId} insights={insights} />

        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {cards.map((card, index) => {
            const Icon = cardIcons[card.type] || Sparkles
            return (
              <article key={`${card.title}-${index}`} className="rounded-lg border bg-white p-4 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-neutral-100">
                      <Icon className="h-4 w-4 text-neutral-700" />
                    </div>
                    <div className="min-w-0">
                      <Badge variant="secondary" className="mb-2 text-[11px] font-normal">
                        {card.type}
                      </Badge>
                      <h3 className="line-clamp-2 text-sm font-semibold leading-5 text-neutral-950">
                        {card.title}
                      </h3>
                    </div>
                  </div>
                </div>
                <p className="mt-3 text-sm leading-6 text-neutral-700">{card.content}</p>
                {card.evidence && (
                  <p className="mt-3 border-l-2 border-neutral-200 pl-3 text-xs leading-5 text-neutral-500">
                    {card.evidence}
                  </p>
                )}
              </article>
            )
          })}
        </div>
      </div>
    </ScrollArea>
  )
}
