import { useEffect, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { toast } from 'react-hot-toast'
import {
  ArrowLeft,
  BookOpenCheck,
  FileText,
  FileUp,
  Loader2,
  Plus,
  SearchCheck,
} from 'lucide-react'
import {
  create_verification_task,
  ingest_paper_pdf,
  ingest_paper_url,
  rerun_verification_task,
  type TaskSnapshot,
} from '@/services/note'
import { useTaskStore } from '@/store/taskStore'
import { useModelStore } from '@/store/modelStore'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

const schema = z.object({
  source: z.string().trim().min(1, '请输入论文 URL'),
  model_name: z.string().min(1, '请选择模型'),
  provider_id: z.string(),
})

type FormValues = z.infer<typeof schema>
type SubmissionMode = 'paper' | 'audit'

const extractFirstUrl = (value: string) => value.match(/https?:\/\/[^\s]+/i)?.[0] || value.trim()

const isHttpUrl = (value: string) => {
  try {
    return ['http:', 'https:'].includes(new URL(extractFirstUrl(value)).protocol)
  }
  catch {
    return false
  }
}

function openView(viewMode: 'source' | 'report' | 'evidence') {
  window.dispatchEvent(new CustomEvent('fastread:workspace-command', {
    detail: { viewMode, chat: false },
  }))
}

export default function NoteForm() {
  const { addPendingTask, currentTaskId, setCurrentTask, getCurrentTask, updateTaskContent } = useTaskStore()
  const { loadEnabledModels, modelList } = useModelStore()
  const currentTask = getCurrentTask()
  const isPaperTask = currentTask?.platform === 'paper' || Boolean(currentTask?.paperDocument)
  const [mode, setMode] = useState<SubmissionMode>('paper')
  const [uploading, setUploading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { source: '', model_name: '', provider_id: '' },
  })
  const selectedModelName = useWatch({ control: form.control, name: 'model_name' })
  const selectedProviderId = useWatch({ control: form.control, name: 'provider_id' })
  const selectedModelId = modelList.find(
    item => item.provider_id === selectedProviderId && item.model_name === selectedModelName
  )?.id || ''

  useEffect(() => {
    loadEnabledModels()
  }, [loadEnabledModels])

  useEffect(() => {
    if (!currentTask) {
      form.reset({
        source: '',
        model_name: modelList[0]?.model_name || '',
        provider_id: modelList[0]?.provider_id || '',
      })
      return
    }
    const reportModel = currentTask.insights?.reading_report?.model
    form.reset({
      source: currentTask.formData?.video_url || currentTask.paperDocument?.source_url || '',
      model_name: currentTask.formData?.model_name || reportModel?.model_name || modelList[0]?.model_name || '',
      provider_id: currentTask.formData?.provider_id || reportModel?.provider_id || modelList[0]?.provider_id || '',
    })
    setMode(isPaperTask ? 'paper' : 'audit')
  }, [currentTaskId, currentTask, form, isPaperTask, modelList])

  useEffect(() => {
    if (currentTaskId || !modelList[0] || form.getValues('model_name')) return
    form.setValue('model_name', modelList[0].model_name)
    form.setValue('provider_id', modelList[0].provider_id)
  }, [currentTaskId, form, modelList])

  const registerPaperSnapshot = (snapshot: TaskSnapshot, sourceLabel: string) => {
    const model = modelList.find(
      item => item.provider_id === form.getValues('provider_id')
        && item.model_name === form.getValues('model_name')
    )
    const taskId = snapshot.id
    addPendingTask(taskId, 'paper', {
      video_url: sourceLabel,
      platform: 'paper',
      input_mode: 'paper',
      quality: 'medium',
      style: 'minimal',
      format: [],
      provider_id: model?.provider_id || '',
      model_name: model?.model_name || '',
    })
    updateTaskContent(taskId, {
      status: snapshot.status,
      message: snapshot.message,
      transcript: snapshot.result?.transcript || snapshot.transcript,
      audioMeta: snapshot.result?.audioMeta || snapshot.audioMeta,
      insights: snapshot.result?.insights || snapshot.insights,
      paperDocument: snapshot.result?.paperDocument,
    })
    setCurrentTask(taskId)
    openView('source')
  }

  const requireModel = () => {
    const model = modelList.find(
      item => item.provider_id === form.getValues('provider_id')
        && item.model_name === form.getValues('model_name')
    )
    if (!model) toast.error('请先在设置中启用一个模型')
    return model
  }

  const uploadPdf = async (file?: File) => {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      toast.error('当前仅支持 PDF 论文')
      return
    }
    const model = requireModel()
    if (!model) return
    setUploading(true)
    try {
      const snapshot = await ingest_paper_pdf({
        file,
        provider_id: model.provider_id,
        model_name: model.model_name,
      })
      registerPaperSnapshot(snapshot, file.name)
      toast.success('PDF 已解析为分页原文')
    }
    catch (error) {
      console.error('论文 PDF 导入失败', error)
      toast.error('PDF 导入失败，请确认文件包含可提取文字')
    }
    finally {
      setUploading(false)
    }
  }

  const submit = async (values: FormValues) => {
    const model = requireModel()
    if (!model) return
    setSubmitting(true)
    try {
      if (isPaperTask) {
        openView('source')
        return
      }

      if (mode === 'paper') {
        if (!isHttpUrl(values.source)) {
          toast.error('请输入可访问的论文详情页或 PDF URL')
          return
        }
        const url = extractFirstUrl(values.source)
        const snapshot = await ingest_paper_url({
          url,
          provider_id: model.provider_id,
          model_name: model.model_name,
        })
        registerPaperSnapshot(snapshot, url)
        toast.success('论文 URL 已解析为分页原文')
        return
      }

      if (currentTaskId) {
        const snapshot = await rerun_verification_task(currentTaskId) as unknown as TaskSnapshot
        const insights = snapshot.result?.insights || snapshot.insights
        updateTaskContent(currentTaskId, {
          status: snapshot.status,
          message: snapshot.message,
          error: snapshot.error,
          ...(insights ? { insights } : {}),
        })
        openView('evidence')
        return
      }

      const inputIsUrl = isHttpUrl(values.source)
      const created = await create_verification_task({
        url: inputIsUrl ? extractFirstUrl(values.source) : '',
        text: inputIsUrl ? '' : values.source,
        max_claims: 50,
        provider_id: model.provider_id,
        model_name: model.model_name,
      }) as unknown as { task_id: string }
      addPendingTask(created.task_id, 'verification', {
        video_url: values.source,
        platform: 'verification',
        input_mode: inputIsUrl ? 'url' : 'text',
        quality: 'medium',
        style: 'minimal',
        format: [],
        provider_id: model.provider_id,
        model_name: model.model_name,
        verification_depth: 'deep',
        source_policy: 'authoritative',
      })
    }
    catch (error) {
      console.error(mode === 'paper' ? '论文 URL 导入失败' : '证据审计失败', error)
      toast.error(mode === 'paper' ? '论文 URL 导入失败，请确认链接可访问' : '证据审计任务提交失败')
    }
    finally {
      setSubmitting(false)
    }
  }

  const createNew = () => {
    setCurrentTask(null)
    setMode('paper')
  }

  if (isPaperTask && currentTask) {
    return (
      <div className="space-y-3">
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-900">
            <FileText className="h-4 w-4" />
            分页原文已就绪
          </div>
          <p className="mt-1 text-xs leading-5 text-emerald-800">
            共 {currentTask.paperDocument?.page_count || currentTask.paperDocument?.pages.length || 0} 页；报告和追问将沿用这些页码。
          </p>
        </div>
        <Button type="button" className="w-full" onClick={() => openView('source')}>
          查看分页原文
        </Button>
        <Button type="button" variant="outline" className="w-full" onClick={() => openView('report')}>
          <BookOpenCheck className="mr-2 h-4 w-4" />
          生成 / 查看关键问题报告
        </Button>
        <Button type="button" variant="ghost" className="w-full text-xs" onClick={createNew}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          导入另一篇论文
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={form.handleSubmit(submit)} className="space-y-4">
      {mode === 'paper' ? (
        <>
          <div className="rounded-md border border-blue-200 bg-blue-50/80 p-3">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-blue-600 text-white">
                <FileUp className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-blue-950">优先导入 PDF</div>
                <p className="mt-0.5 text-xs leading-5 text-blue-800">直接保留每一页的原文，是报告引用和后续追问的证据底座。</p>
                <label className={`mt-2 inline-flex h-8 cursor-pointer items-center rounded-md border border-blue-300 bg-white px-3 text-xs font-semibold text-blue-800 hover:bg-blue-100 ${uploading ? 'pointer-events-none opacity-60' : ''}`}>
                  {uploading ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <FileUp className="mr-1.5 h-3.5 w-3.5" />}
                  {uploading ? '正在逐页解析…' : '选择 PDF 并导入'}
                  <input
                    type="file"
                    accept="application/pdf,.pdf"
                    className="hidden"
                    disabled={uploading}
                    onChange={event => {
                      const file = event.target.files?.[0]
                      event.target.value = ''
                      uploadPdf(file)
                    }}
                  />
                </label>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 text-[10px] uppercase tracking-[0.14em] text-slate-400">
            <span className="h-px flex-1 bg-slate-200" /> 或使用论文 URL <span className="h-px flex-1 bg-slate-200" />
          </div>
        </>
      ) : (
        <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold text-slate-800">独立证据审计</div>
              <p className="mt-1 text-xs leading-5 text-slate-500">该入口只核查网页或文本主张，不属于论文阅读主流程。</p>
            </div>
            <button type="button" onClick={() => setMode('paper')} className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-900">
              <ArrowLeft className="h-3.5 w-3.5" /> 回到论文
            </button>
          </div>
        </div>
      )}

      <div>
        <label htmlFor="paper-source" className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          {mode === 'paper' ? '论文详情页或 PDF URL' : '待审计网页或文本'}
        </label>
        <Textarea
          id="paper-source"
          className="mt-2 min-h-28 resize-y text-xs leading-5"
          placeholder={mode === 'paper'
            ? 'https://example.org/paper.pdf'
            : '粘贴网页 URL，或输入需要外部证据核查的主张'}
          {...form.register('source')}
        />
        {form.formState.errors.source && (
          <p className="mt-1 text-xs text-red-600">{form.formState.errors.source.message}</p>
        )}
      </div>

      <div>
        <label className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">阅读模型</label>
        {modelList.length ? (
          <Select
            value={selectedModelId}
            onValueChange={modelId => {
              const model = modelList.find(item => item.id === modelId)
              if (!model) return
              form.setValue('model_name', model.model_name)
              form.setValue('provider_id', model.provider_id)
            }}
          >
            <SelectTrigger className="mt-2 w-full">
              <SelectValue placeholder="选择模型" />
            </SelectTrigger>
            <SelectContent>
              {modelList.map(model => (
                <SelectItem key={model.id} value={model.id}>
                  <span>{model.model_name}</span>
                  <span className="ml-2 font-mono text-[10px] text-slate-400">{model.provider_id}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">请先在设置中启用模型。</p>
        )}
      </div>

      <Button type="submit" className="w-full" disabled={submitting || uploading || !modelList.length}>
        {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : mode === 'paper' ? <BookOpenCheck className="mr-2 h-4 w-4" /> : <SearchCheck className="mr-2 h-4 w-4" />}
        {submitting ? '正在处理…' : mode === 'paper' ? '导入论文 URL' : currentTaskId ? '重新运行证据审计' : '开始证据审计'}
      </Button>

      {mode === 'paper' && (
        <button
          type="button"
          onClick={() => setMode('audit')}
          className="w-full text-center text-[11px] text-slate-400 underline-offset-4 hover:text-slate-700 hover:underline"
        >
          可选：切换到独立网页 / 文本证据审计
        </button>
      )}
      {mode === 'audit' && currentTaskId && (
        <Button type="button" variant="ghost" className="w-full text-xs" onClick={createNew}>
          <Plus className="mr-1.5 h-3.5 w-3.5" /> 新建任务
        </Button>
      )}
    </form>
  )
}
