import { useEffect, useState } from 'react'
import { ArrowRight, Loader2, MessageSquareText, Save, Sparkles } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { save_personal_summary } from '@/services/note'
import { useTaskStore, type Task } from '@/store/taskStore'

function openView(viewMode: 'report' | 'chat') {
  window.dispatchEvent(new CustomEvent('fastread:workspace-command', {
    detail: { viewMode, chat: viewMode === 'chat' ? 'full' : false },
  }))
}

export default function PersonalSummaryView({ task }: { task: Task | null }) {
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)
  const [summary, setSummary] = useState(task?.insights?.personal_summary?.content || '')
  const [saving, setSaving] = useState(false)
  const report = task?.insights?.reading_report

  useEffect(() => {
    setSummary(task?.insights?.personal_summary?.content || '')
  }, [task?.id, task?.insights?.personal_summary?.content])

  const save = async () => {
    if (!task) return
    setSaving(true)
    try {
      const response = await save_personal_summary(task.id, summary)
      updateTaskContent(task.id, {
        insights: {
          ...(task.insights || { version: 1, scores: {}, cards: [] }),
          personal_summary: response.personal_summary,
        },
      })
      toast.success('300 字总结已保存')
    }
    finally {
      setSaving(false)
    }
  }

  if (!task) {
    return <div className="flex h-full items-center justify-center text-sm text-slate-500">请先导入论文。</div>
  }

  return (
    <div className="h-full overflow-y-auto bg-slate-50/50 p-6">
      <div className="mx-auto max-w-3xl space-y-4">
        <header className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-slate-900 text-white">
            <Sparkles className="h-4 w-4" />
          </div>
          <h1 className="mt-4 text-xl font-semibold text-slate-950">用自己的话写 300 字总结</h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            先压缩研究问题，再写方法主线与最重要贡献，最后留下一个仍需追问的疑点。个人总结与 AI 报告分开保存。
          </p>
          {!report && (
            <button
              type="button"
              onClick={() => openView('report')}
              className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-blue-700 hover:underline"
            >
              先生成关键问题报告 <ArrowRight className="h-3.5 w-3.5" />
            </button>
          )}
        </header>

        <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <label htmlFor="personal-summary" className="text-sm font-semibold text-slate-900">我的总结</label>
            <span className={`font-mono text-xs ${summary.length > 280 ? 'text-amber-700' : 'text-slate-400'}`}>
              {summary.length}/300
            </span>
          </div>
          <Textarea
            id="personal-summary"
            value={summary}
            maxLength={300}
            onChange={event => setSummary(event.target.value.slice(0, 300))}
            className="mt-3 min-h-52 resize-y text-sm leading-7"
            placeholder="这篇论文试图解决……；作者通过……；最重要的贡献是……；我仍不确定……"
          />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-slate-500">保存后仍可继续修改，不会覆盖 AI 阅读报告。</p>
            <Button size="sm" onClick={save} disabled={saving}>
              {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
              保存总结
            </Button>
          </div>
        </section>

        <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4">
          <div>
            <div className="text-sm font-semibold text-blue-950">总结完成后，带着页码继续追问</div>
            <p className="mt-1 text-xs text-blue-800">回答优先检索分页原文；找不到支撑页面时会明确说明证据不足。</p>
          </div>
          <Button size="sm" onClick={() => openView('chat')}>
            <MessageSquareText className="mr-1.5 h-3.5 w-3.5" />
            带页码持续追问
          </Button>
        </section>
      </div>
    </div>
  )
}
