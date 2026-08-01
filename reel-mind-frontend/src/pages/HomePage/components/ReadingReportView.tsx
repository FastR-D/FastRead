import { useEffect, useMemo, useState } from 'react'
import {
  BookOpenCheck,
  ExternalLink,
  FileQuestion,
  Loader2,
  MessageSquareText,
  RefreshCw,
  Save,
  ShieldCheck,
} from 'lucide-react'
import { toast } from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  generate_reading_report,
  resolve_backend_resource_url,
  save_personal_summary,
} from '@/services/note'
import { useModelStore } from '@/store/modelStore'
import { useTaskStore, type ReadingReport, type Task } from '@/store/taskStore'

const STATUS_LABELS: Record<string, string> = {
  source_only: '原文内陈述',
  supported: '外部证据支持',
  refuted: '外部证据反驳',
  mixed: '证据存在冲突',
  insufficient: '证据不足',
  data_void: '数据空缺',
  source_risk: '信源风险',
}

const STATUS_TONES: Record<string, string> = {
  supported: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  refuted: 'border-red-200 bg-red-50 text-red-700',
  mixed: 'border-amber-200 bg-amber-50 text-amber-700',
  source_only: 'border-blue-200 bg-blue-50 text-blue-700',
  insufficient: 'border-slate-200 bg-slate-50 text-slate-600',
}

function emitChat() {
  window.dispatchEvent(new CustomEvent('reelmind:workspace-command', {
    detail: { viewMode: 'report', chat: 'half' },
  }))
}

function AcademicGateBadge({ report }: { report: ReadingReport }) {
  const gate = report.academic_gate
  const passed = gate?.gate_passed
  return (
    <div className={`rounded-md border px-3 py-2 text-xs ${
      passed
        ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
        : 'border-amber-200 bg-amber-50 text-amber-900'
    }`}>
      <div className="flex items-center gap-2 font-semibold">
        <ShieldCheck className="h-4 w-4" />
        身份 Gate {gate?.level || 'N/A'} · {gate?.label || '未识别论文身份'}
      </div>
      <p className="mt-1 leading-5">
        {passed
          ? '身份资料通过 Gate；这不等同于论文主张已被外部证据核实。'
          : (
            <>
          未通过四大安全顶会正式论文 Gate；报告只描述原文，不把单篇材料升级为领域共识。
            </>
          )}
      </p>
    </div>
  )
}

function GroundingBadge({ status }: { status?: string }) {
  if (!status) return null
  const grounded = status === 'source_grounded'
  return (
    <div className={`rounded-md border px-3 py-2 text-xs ${
      grounded
        ? 'border-blue-200 bg-blue-50 text-blue-800'
        : 'border-amber-200 bg-amber-50 text-amber-900'
    }`}>
      {grounded ? '原文已定位' : '报告未完全落源'}
    </div>
  )
}

function EvidenceQuotes({ evidence }: { evidence: NonNullable<ReadingReport['contributions'][number]['evidence']> }) {
  if (typeof evidence === 'string') {
    return <p className="mt-1 text-xs text-slate-500">依据：{evidence}</p>
  }

  return (
    <div className="mt-2 space-y-2">
      {evidence.map((item, index) => {
        const sourceHref = resolve_backend_resource_url(item.source_url)
        return (
          <blockquote key={`${item.source_id || item.source_url || index}`} className="border-l-2 border-blue-300 pl-3 text-xs leading-5 text-slate-600">
            “{item.exact_quote}”
            <div className="mt-1 flex items-center gap-2 font-mono text-[10px] text-slate-400">
              {item.page_start ? `第 ${item.page_start}${item.page_end && item.page_end !== item.page_start ? `–${item.page_end}` : ''} 页` : '正文证据'}
              {sourceHref && (
                <a href={sourceHref} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-blue-600 hover:underline">
                  原文 <ExternalLink className="h-2.5 w-2.5" />
                </a>
              )}
            </div>
          </blockquote>
        )
      })}
    </div>
  )
}

export default function ReadingReportView({ task }: { task: Task | null }) {
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)
  const { modelList, loadEnabledModels } = useModelStore()
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const report = task?.insights?.reading_report
  const [personalSummary, setPersonalSummary] = useState(
    task?.insights?.personal_summary?.content || '',
  )

  useEffect(() => {
    loadEnabledModels()
  }, [loadEnabledModels])

  useEffect(() => {
    setPersonalSummary(task?.insights?.personal_summary?.content || '')
  }, [task?.id, task?.insights?.personal_summary?.content])

  const model = useMemo(() => {
    const preferredProviderId = task?.formData?.provider_id || report?.model?.provider_id
    const preferredModelName = task?.formData?.model_name || report?.model?.model_name
    if (preferredProviderId || preferredModelName) {
      return modelList.find(item =>
        item.provider_id === preferredProviderId && item.model_name === preferredModelName
      )
    }
    return modelList[0]
  }, [modelList, report?.model?.model_name, report?.model?.provider_id, task?.formData?.model_name, task?.formData?.provider_id])

  const handleGenerate = async (force = false) => {
    if (!task || !model?.provider_id || !model?.model_name) {
      toast.error('请先在设置中启用一个模型')
      return
    }
    setGenerating(true)
    try {
      const response = await generate_reading_report({
        task_id: task.id,
        provider_id: model.provider_id,
        model_name: model.model_name,
        force,
      })
      updateTaskContent(task.id, {
        insights: {
          ...(task.insights || { version: 1, scores: {}, cards: [] }),
          reading_report: response.reading_report,
        },
      })
      toast.success('关键问题阅读报告已生成')
    }
    finally {
      setGenerating(false)
    }
  }

  const handleSaveSummary = async () => {
    if (!task) return
    setSaving(true)
    try {
      const response = await save_personal_summary(task.id, personalSummary)
      updateTaskContent(task.id, {
        insights: {
          ...(task.insights || { version: 1, scores: {}, cards: [] }),
          personal_summary: response.personal_summary,
        },
      })
      toast.success('个人总结已保存')
    }
    finally {
      setSaving(false)
    }
  }

  if (!task) {
    return (
      <div className="flex h-full w-full items-center justify-center text-sm text-slate-500">
        请先导入 PDF，或提交论文 URL / 原文。
      </div>
    )
  }

  if (!report) {
    return (
      <div className="flex h-full w-full items-center justify-center overflow-y-auto p-6">
        <div className="w-full max-w-2xl rounded-lg border border-slate-200 bg-white p-7 shadow-sm">
          <div className="flex h-11 w-11 items-center justify-center rounded-md bg-slate-900 text-white">
            <FileQuestion className="h-5 w-5" />
          </div>
          <h2 className="mt-4 text-xl font-semibold text-slate-900">一键生成关键问题阅读报告</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            按 NotebookLM 式理解路径，固定回答研究问题、方法过程、主要贡献、实验与局限；引用必须能匹配论文原文页码或已抽取证据。
          </p>
          <div className="mt-5 grid gap-2 text-sm text-slate-700 sm:grid-cols-2">
            {['研究问题是什么', '方法如何一步步完成', '主要贡献相对已有工作是什么', '实验依据与局限在哪里'].map(item => (
              <div key={item} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                {item}
              </div>
            ))}
          </div>
          <Button
            className="mt-6 w-full"
            disabled={generating || !model}
            onClick={() => handleGenerate(false)}
          >
            {generating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <BookOpenCheck className="mr-2 h-4 w-4" />}
            {generating ? '正在生成学术阅读报告…' : '一键生成阅读报告'}
          </Button>
          {!model && <p className="mt-2 text-center text-xs text-amber-700">请先在设置中启用模型</p>}
        </div>
      </div>
    )
  }

  return (
    <div className="h-full w-full overflow-y-auto bg-slate-50/50">
      <article className="mx-auto max-w-5xl space-y-6 p-6 pb-16">
        <header className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">FastRead · Guided Report</div>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">{report.title}</h1>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => handleGenerate(true)} disabled={generating}>
                <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${generating ? 'animate-spin' : ''}`} />
                重新生成
              </Button>
              <Button size="sm" onClick={emitChat}>
                <MessageSquareText className="mr-1.5 h-3.5 w-3.5" />
                继续追问
              </Button>
            </div>
          </div>
          <p className="mt-5 whitespace-pre-wrap text-[15px] leading-7 text-slate-700">{report.executive_summary}</p>
          <div className="mt-5 space-y-2">
            <AcademicGateBadge report={report} />
            <GroundingBadge status={report.report_grounding_status} />
          </div>
        </header>

        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-slate-500">关键问题</h2>
          <div className="space-y-3">
            {report.key_questions.map((item, index) => (
              <div key={`${item.question}-${index}`} className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <h3 className="max-w-3xl text-base font-semibold text-slate-900">
                    <span className="mr-2 font-mono text-slate-400">Q{index + 1}</span>{item.question}
                  </h3>
                  <span className={`rounded-sm border px-2 py-0.5 text-[11px] font-medium ${STATUS_TONES[item.verification_status] || STATUS_TONES.insufficient}`}>
                    {STATUS_LABELS[item.verification_status] || item.verification_status}
                  </span>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-700">{item.answer}</p>
                <p className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600">
                  <strong>为什么重要：</strong>{item.why_it_matters}
                </p>
                {item.evidence.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {item.evidence.map((evidence, evidenceIndex) => {
                      const sourceHref = resolve_backend_resource_url(evidence.source_url)
                      return (
                        <blockquote key={evidenceIndex} className="border-l-2 border-blue-300 pl-3 text-xs leading-5 text-slate-600">
                          “{evidence.exact_quote}”
                          <div className="mt-1 flex items-center gap-2 font-mono text-[10px] text-slate-400">
                            {evidence.page_start ? `第 ${evidence.page_start}${evidence.page_end && evidence.page_end !== evidence.page_start ? `–${evidence.page_end}` : ''} 页` : '正文证据'}
                            {sourceHref && (
                              <a href={sourceHref} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-blue-600 hover:underline">
                                原文 <ExternalLink className="h-2.5 w-2.5" />
                              </a>
                            )}
                          </div>
                        </blockquote>
                      )
                    })}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        <div className="grid gap-4 lg:grid-cols-2">
          <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">主要过程</h2>
            <ol className="mt-3 space-y-3">
              {report.process.map((item, index) => (
                <li key={`${item.step}-${index}`} className="flex gap-3 text-sm leading-6 text-slate-700">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-900 font-mono text-[11px] text-white">{index + 1}</span>
                  <div><strong>{item.step}</strong><p>{item.description}</p></div>
                </li>
              ))}
            </ol>
          </section>
          <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">主要贡献</h2>
            <div className="mt-3 space-y-3">
              {report.contributions.map((item, index) => (
                <div key={`${item.title}-${index}`} className="text-sm leading-6 text-slate-700">
                  <strong>{item.title}</strong><p>{item.description}</p>
                  {item.evidence && <EvidenceQuotes evidence={item.evidence} />}
                </div>
              ))}
            </div>
          </section>
        </div>

        <section className="rounded-lg border border-amber-200 bg-amber-50 p-5">
          <h2 className="text-sm font-semibold text-amber-950">局限与证据边界</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-amber-900">
            {report.limitations.map((item, index) => <li key={index}>{item}</li>)}
          </ul>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">我的总结</h2>
              <p className="mt-1 text-xs text-slate-500">只记最重要的结论，限制 300 字；与 AI 报告分开保存。</p>
            </div>
            <span className={`font-mono text-xs ${personalSummary.length > 280 ? 'text-amber-700' : 'text-slate-400'}`}>{personalSummary.length}/300</span>
          </div>
          <Textarea
            className="mt-3 min-h-28 resize-y"
            maxLength={300}
            value={personalSummary}
            onChange={event => setPersonalSummary(event.target.value.slice(0, 300))}
            placeholder="用自己的话记录研究问题、方法、贡献和你仍不确定的地方……"
          />
          <Button className="mt-3" size="sm" onClick={handleSaveSummary} disabled={saving}>
            {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
            保存总结
          </Button>
        </section>
      </article>
    </div>
  )
}
