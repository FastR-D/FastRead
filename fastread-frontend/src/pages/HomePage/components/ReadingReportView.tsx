import { useEffect, useMemo, useState } from 'react'
import {
  BookOpenCheck,
  ArrowRight,
  ExternalLink,
  FileQuestion,
  Loader2,
  MessageSquareText,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react'
import { toast } from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import {
  generate_reading_report,
  resolve_backend_resource_url,
} from '@/services/note'
import { useModelStore } from '@/store/modelStore'
import { useTaskStore, type ReadingReport, type Task } from '@/store/taskStore'
import { emitWorkspaceCommand } from '@/utils/workspaceNavigation'

function emitChat() {
  window.dispatchEvent(new CustomEvent('fastread:workspace-command', {
    detail: { viewMode: 'chat', chat: 'full' },
  }))
}

function emitSummary() {
  window.dispatchEvent(new CustomEvent('fastread:workspace-command', {
    detail: { viewMode: 'summary', chat: false },
  }))
}

function openEvidenceInSource(taskId: string, page?: number | null, quote?: string) {
  if (!page) return
  emitWorkspaceCommand({ taskId, viewMode: 'source', page, quote })
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
          ? '已命中安全、系统或 AI 核心顶会，且正式身份资料通过 Gate；这不等同于论文主张已被外部证据核实。'
          : gate?.is_core_venue
            ? `已识别 ${gate.venue?.short_name || gate.venue?.name || '核心顶会'}；论文内声明已展示，仍需官方会议记录闭合正式身份。`
          : (
            <>
          未通过安全、系统或 AI 核心顶会正式身份 Gate；报告只描述原文，不把单篇材料升级为领域共识。
            </>
          )}
      </p>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
        {gate?.venue?.short_name && <span>{gate.venue.short_name}{gate.year ? ` ${gate.year}` : ''} · {gate.venue_track || gate.venue.track}</span>}
        {gate?.authors?.length ? <span>{gate.authors.join('、')}</span> : null}
        {gate?.registry_record_url && (
          <a href={gate.registry_record_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold underline underline-offset-2">
            正式记录 <ExternalLink className="h-3 w-3" />
          </a>
        )}
        <span>闭合状态：{gate?.identity_status || 'incomplete'}</span>
      </div>
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

function EvidenceQuotes({
  evidence,
  taskId,
}: {
  evidence: NonNullable<ReadingReport['contributions'][number]['evidence']>
  taskId: string
}) {
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
            <div className="mt-1 flex flex-wrap items-center gap-2 font-mono text-[10px] text-slate-400">
              {item.page_start ? (
                <button
                  type="button"
                  onClick={() => openEvidenceInSource(taskId, item.page_start, item.exact_quote)}
                  className="font-semibold text-blue-700 hover:underline"
                  title="在分页原文中定位并高亮"
                >
                  第 {item.page_start}{item.page_end && item.page_end !== item.page_start ? `–${item.page_end}` : ''} 页 · 定位原句
                </button>
              ) : '正文证据'}
              {sourceHref && (
                <a href={sourceHref} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-blue-600 hover:underline">
                  打开 PDF <ExternalLink className="h-2.5 w-2.5" />
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
  const report = task?.insights?.reading_report

  useEffect(() => {
    loadEnabledModels()
  }, [loadEnabledModels])

  const model = useMemo(() => {
    const preferredProviderId = task?.paperInput.provider_id || report?.model?.provider_id
    const preferredModelName = task?.paperInput.model_name || report?.model?.model_name
    if (preferredProviderId || preferredModelName) {
      return modelList.find(item =>
        item.provider_id === preferredProviderId && item.model_name === preferredModelName
      )
    }
    return modelList[0]
  }, [modelList, report?.model?.model_name, report?.model?.provider_id, task?.paperInput.model_name, task?.paperInput.provider_id])

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
          ...(task.insights || { version: 1 }),
          reading_report: response.reading_report,
        },
      })
      toast.success('关键问题阅读报告已生成')
    }
    finally {
      setGenerating(false)
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

        <section className="rounded-lg border border-slate-200 bg-white px-6 py-2 shadow-sm">
          <h2 className="border-b border-slate-100 py-4 text-sm font-semibold uppercase tracking-[0.14em] text-slate-500">关键问题与回答</h2>
          <div className="divide-y divide-slate-100">
            {report.key_questions.map((item, index) => (
              <div key={`${item.question}-${index}`} className="py-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <h3 className="max-w-3xl text-base font-semibold text-slate-900">
                    <span className="mr-2 font-mono text-blue-600">{String(index + 1).padStart(2, '0')}</span>{item.question}
                  </h3>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-700">{item.answer}</p>
                <p className="mt-3 border-l-2 border-slate-200 pl-3 text-xs leading-5 text-slate-600">
                  <strong>阅读提示：</strong>{item.why_it_matters}
                </p>
                {item.evidence.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {item.evidence.map((evidence, evidenceIndex) => {
                      const sourceHref = resolve_backend_resource_url(evidence.source_url)
                      return (
                        <blockquote key={evidenceIndex} className="border-l-2 border-blue-300 pl-3 text-xs leading-5 text-slate-600">
                          “{evidence.exact_quote}”
                          <div className="mt-1 flex flex-wrap items-center gap-2 font-mono text-[10px] text-slate-400">
                            {evidence.page_start ? (
                              <button
                                type="button"
                                onClick={() => openEvidenceInSource(task.id, evidence.page_start, evidence.exact_quote)}
                                className="font-semibold text-blue-700 hover:underline"
                                title="在分页原文中定位并高亮"
                              >
                                第 {evidence.page_start}{evidence.page_end && evidence.page_end !== evidence.page_start ? `–${evidence.page_end}` : ''} 页 · 定位原句
                              </button>
                            ) : '正文证据'}
                            {sourceHref && (
                              <a href={sourceHref} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-blue-600 hover:underline">
                                打开 PDF <ExternalLink className="h-2.5 w-2.5" />
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

        <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <section className="border-b border-slate-100 p-6">
            <h2 className="text-lg font-semibold text-slate-900">论文如何一步步完成这项工作</h2>
            <ol className="mt-3 space-y-3">
              {report.process.map((item, index) => (
                <li key={`${item.step}-${index}`} className="flex gap-3 text-sm leading-6 text-slate-700">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-900 font-mono text-[11px] text-white">{index + 1}</span>
                  <div><strong>{item.step}</strong><p>{item.description}</p></div>
                </li>
              ))}
            </ol>
          </section>
          <section className="p-6">
            <h2 className="text-lg font-semibold text-slate-900">论文真正增加了什么</h2>
            <div className="mt-4 divide-y divide-slate-100">
              {report.contributions.map((item, index) => (
                <div key={`${item.title}-${index}`} className="py-4 first:pt-0 last:pb-0 text-sm leading-6 text-slate-700">
                  <strong>{item.title}</strong><p>{item.description}</p>
                  {item.evidence && <EvidenceQuotes evidence={item.evidence} taskId={task.id} />}
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

        {report.terms.length > 0 && (
          <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">关键术语</h2>
            <dl className="mt-3 grid gap-3 sm:grid-cols-2">
              {report.terms.map((item, index) => (
                <div key={`${item.term}-${index}`} className="rounded-md bg-slate-50 px-3 py-2.5">
                  <dt className="text-xs font-semibold text-slate-800">{item.term}</dt>
                  <dd className="mt-1 text-xs leading-5 text-slate-600">{item.explanation}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        <section className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-blue-200 bg-blue-50 p-5">
          <div>
            <h2 className="text-sm font-semibold text-blue-950">下一步：压缩成自己的 300 字总结</h2>
            <p className="mt-1 text-xs leading-5 text-blue-800">先写下你真正理解的研究问题、方法与贡献，再带着疑点持续追问。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={emitChat}>
              追问不懂的细节 <MessageSquareText className="ml-1.5 h-3.5 w-3.5" />
            </Button>
            <Button size="sm" onClick={emitSummary}>
              写 300 字总结 <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
            </Button>
          </div>
        </section>
      </article>
    </div>
  )
}
