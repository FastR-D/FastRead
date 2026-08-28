import { useEffect, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { toast } from 'react-hot-toast'
import { BookOpenCheck, FileText, FileUp, Loader2, Plus } from 'lucide-react'
import { ingest_paper_pdf, ingest_paper_url, type TaskSnapshot } from '@/services/note'
import { useTaskStore } from '@/store/taskStore'
import { useModelStore } from '@/store/modelStore'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { paperImportModelFields } from '@/utils/paperImport'

const schema = z.object({
  source: z.string().trim().min(1, '请输入论文 URL'),
  model_name: z.string(),
  provider_id: z.string(),
})

type FormValues = z.infer<typeof schema>

const extractFirstUrl = (value: string) => value.match(/https?:\/\/[^\s]+/i)?.[0] || value.trim()

const isHttpUrl = (value: string) => {
  try {
    return ['http:', 'https:'].includes(new URL(extractFirstUrl(value)).protocol)
  }
  catch {
    return false
  }
}

function openView(viewMode: 'source' | 'report') {
  window.dispatchEvent(new CustomEvent('fastread:workspace-command', {
    detail: { viewMode, chat: false },
  }))
}

export default function NoteForm() {
  const { applyTaskSnapshot, currentTaskId, setCurrentTask, getCurrentTask } = useTaskStore()
  const { loadEnabledModels, modelList } = useModelStore()
  const currentTask = getCurrentTask()
  const [uploading, setUploading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { source: '', model_name: '', provider_id: '' },
  })
  const selectedModelName = useWatch({ control: form.control, name: 'model_name' })
  const selectedProviderId = useWatch({ control: form.control, name: 'provider_id' })
  const selectedModelId = modelList.find(
    item => item.provider_id === selectedProviderId && item.model_name === selectedModelName,
  )?.id || ''

  useEffect(() => {
    loadEnabledModels()
  }, [loadEnabledModels])

  useEffect(() => {
    const reportModel = currentTask?.insights?.reading_report?.model
    form.reset({
      source: currentTask?.paperInput.source_url || '',
      model_name: currentTask?.paperInput.model_name || reportModel?.model_name || modelList[0]?.model_name || '',
      provider_id: currentTask?.paperInput.provider_id || reportModel?.provider_id || modelList[0]?.provider_id || '',
    })
  }, [currentTask, currentTaskId, form, modelList])

  const registerPaper = (snapshot: TaskSnapshot, sourceLabel: string) => {
    const model = modelList.find(
      item => item.provider_id === form.getValues('provider_id')
        && item.model_name === form.getValues('model_name'),
    )
    applyTaskSnapshot(snapshot, {
      source_url: sourceLabel,
      filename: snapshot.paperDocument?.filename,
      ...paperImportModelFields(model),
    })
    setCurrentTask(snapshot.id)
    openView('source')
  }

  const uploadPdf = async (file?: File) => {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      toast.error('当前仅支持 PDF 论文')
      return
    }
    const model = modelList.find(
      item => item.provider_id === form.getValues('provider_id')
        && item.model_name === form.getValues('model_name'),
    )
    setUploading(true)
    try {
      registerPaper(await ingest_paper_pdf({ file, ...paperImportModelFields(model) }), file.name)
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
    if (currentTask) {
      openView('source')
      return
    }
    if (!isHttpUrl(values.source)) {
      toast.error('请输入可访问的论文详情页或 PDF URL')
      return
    }
    setSubmitting(true)
    try {
      const url = extractFirstUrl(values.source)
      const model = modelList.find(
        item => item.provider_id === values.provider_id && item.model_name === values.model_name,
      )
      registerPaper(await ingest_paper_url({ url, ...paperImportModelFields(model) }), url)
      toast.success('论文 URL 已解析为分页原文')
    }
    catch (error) {
      console.error('论文 URL 导入失败', error)
      toast.error('论文 URL 导入失败，请确认链接可访问')
    }
    finally {
      setSubmitting(false)
    }
  }

  const createNew = () => setCurrentTask(null)

  if (currentTask) {
    return (
      <div className="space-y-3">
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-900">
            <FileText className="h-4 w-4" />分页原文已就绪
          </div>
          <p className="mt-1 text-xs leading-5 text-emerald-800">
            共 {currentTask.paperDocument?.page_count || currentTask.paperDocument?.pages.length || 0} 页；报告、近邻论文与追问沿用同一论文身份。
          </p>
        </div>
        <Button type="button" className="w-full" onClick={() => openView('source')}>查看分页原文</Button>
        <Button type="button" variant="outline" className="w-full" onClick={() => openView('report')}>
          <BookOpenCheck className="mr-2 h-4 w-4" />生成 / 查看关键问题报告
        </Button>
        <Button type="button" variant="ghost" className="w-full text-xs" onClick={createNew}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />导入另一篇论文
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={form.handleSubmit(submit)} className="space-y-4">
      <div className="rounded-md border border-blue-200 bg-blue-50/80 p-3">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-blue-600 text-white"><FileUp className="h-4 w-4" /></div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-blue-950">优先导入 PDF</div>
            <p className="mt-0.5 text-xs leading-5 text-blue-800">直接保留每页原文，作为报告引用和持续追问的底座。</p>
            <label className={`mt-2 inline-flex h-8 cursor-pointer items-center rounded-md border border-blue-300 bg-white px-3 text-xs font-semibold text-blue-800 hover:bg-blue-100 ${uploading ? 'pointer-events-none opacity-60' : ''}`}>
              {uploading ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <FileUp className="mr-1.5 h-3.5 w-3.5" />}
              {uploading ? '正在逐页解析…' : '选择 PDF 并导入'}
              <input type="file" accept="application/pdf,.pdf" className="hidden" disabled={uploading} onChange={event => {
                const file = event.target.files?.[0]
                event.target.value = ''
                void uploadPdf(file)
              }} />
            </label>
          </div>
        </div>
      </div>

      <div>
        <label htmlFor="paper-source" className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">论文详情页或 PDF URL</label>
        <Textarea id="paper-source" className="mt-2 min-h-24 resize-y text-xs leading-5" placeholder="https://example.org/paper.pdf" {...form.register('source')} />
        {form.formState.errors.source && <p className="mt-1 text-xs text-red-600">{form.formState.errors.source.message}</p>}
      </div>

      <div>
        <label className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">阅读模型（可稍后配置）</label>
        {modelList.length ? (
          <Select value={selectedModelId} onValueChange={modelId => {
            const model = modelList.find(item => item.id === modelId)
            if (!model) return
            form.setValue('model_name', model.model_name)
            form.setValue('provider_id', model.provider_id)
          }}>
            <SelectTrigger className="mt-2 w-full"><SelectValue placeholder="选择模型" /></SelectTrigger>
            <SelectContent>{modelList.map(model => (
              <SelectItem key={model.id} value={model.id}>
                <span>{model.model_name}</span><span className="ml-2 font-mono text-[10px] text-slate-400">{model.provider_id}</span>
              </SelectItem>
            ))}</SelectContent>
          </Select>
        ) : (
          <p className="mt-2 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs leading-5 text-blue-800">
            无模型也可导入并逐页阅读；生成报告和持续追问时再到设置中启用模型。
          </p>
        )}
      </div>

      <Button type="submit" className="w-full" disabled={submitting || uploading}>
        {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <BookOpenCheck className="mr-2 h-4 w-4" />}
        {submitting ? '正在处理…' : '导入论文 URL'}
      </Button>
    </form>
  )
}
