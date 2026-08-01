/* NoteForm.tsx ---------------------------------------------------- */
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form.tsx'
import { useEffect, useState } from 'react'
import { type FieldErrors, useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { toast } from 'react-hot-toast'

import { BookOpenCheck, ChevronDown, FileUp, Info, Loader2, Plus, SearchCheck } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert.tsx'
import {
  create_verification_task,
  ingest_paper_pdf,
  ingest_paper_url,
  rerun_verification_task,
  type TaskSnapshot,
} from '@/services/note.ts'
import { useTaskStore } from '@/store/taskStore'
import { useModelStore } from '@/store/modelStore'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip.tsx'
import { Checkbox } from '@/components/ui/checkbox.tsx'
import { Button } from '@/components/ui/button.tsx'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select.tsx'
import { Input } from '@/components/ui/input.tsx'
import { Textarea } from '@/components/ui/textarea.tsx'
import { noteStyles, noteFormats, videoPlatforms } from '@/constant/note.ts'
import { useNavigate } from 'react-router-dom'

const extractFirstUrl = (value: string) =>
  value.match(/https?:\/\/[^\s]+/i)?.[0] ?? value

const isHttpUrl = (value: string) => {
  try {
    const url = new URL(extractFirstUrl(value))
    return ['http:', 'https:'].includes(url.protocol)
  }
  catch {
    return false
  }
}

/* -------------------- 校验 Schema -------------------- */
const formSchema = z
  .object({
    video_url: z.string().optional(),
    platform: z.enum(['douyin', 'bilibili', 'kuaishou']),
    quality: z.enum(['fast', 'medium', 'slow']),
    screenshot: z.boolean().optional(),
    link: z.boolean().optional(),
    model_name: z.string().nonempty('请选择模型'),
    provider_id: z.string().default(''),
    format: z.array(z.string()).default([]),
    style: z.string().default('minimal'),
    extras: z.string().optional(),
    collection_folder: z.string().optional(),
    collection_tags: z.string().optional(),
    collection_note: z.string().optional(),
    video_understanding: z.boolean().optional(),
    video_interval: z.coerce.number().min(1).max(30).default(6).optional(),
    grid_size: z
      .tuple([z.coerce.number().min(1).max(10), z.coerce.number().min(1).max(10)])
      .default([2, 2])
      .optional(),
  })
  .superRefine(({ video_url }, ctx) => {
    if (!video_url) {
      ctx.addIssue({ code: 'custom', message: '核实内容不能为空', path: ['video_url'] })
      return
    }
  })

export type NoteFormValues = z.infer<typeof formSchema>

const createEmptyFormValues = (modelName = '', providerId = ''): NoteFormValues => ({
  platform: 'douyin',
  quality: 'medium',
  model_name: modelName,
  provider_id: providerId,
  style: 'minimal',
  video_interval: 6,
  grid_size: [2, 2],
  format: [],
  collection_folder: '核验历史',
  collection_tags: '',
  collection_note: '',
  video_url: '',
  extras: '',
  screenshot: false,
  link: false,
  video_understanding: false,
})

/* -------------------- 可复用子组件 -------------------- */
const SectionHeader = ({ title, tip }: { title: string; tip?: string }) => (
  <div className="mb-2 flex items-center justify-between">
    <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{title}</h3>
    {tip && (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Info className="h-3.5 w-3.5 cursor-pointer text-slate-300 transition hover:text-slate-500" />
          </TooltipTrigger>
          <TooltipContent className="text-xs">{tip}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )}
  </div>
)

const CheckboxGroup = ({
  value = [],
  onChange,
  disabledMap,
}: {
  value?: string[]
  onChange: (v: string[]) => void
  disabledMap: Record<string, boolean>
}) => (
  <div className="flex flex-wrap gap-x-3 gap-y-2">
    {noteFormats.map(({ label, value: v }) => (
      <label key={v} className="flex items-center gap-1.5 text-sm text-slate-700">
        <Checkbox
          checked={value.includes(v)}
          disabled={disabledMap[v]}
          onCheckedChange={checked =>
            onChange(checked ? [...value, v] : value.filter(x => x !== v))
          }
        />
        <span>{label}</span>
      </label>
    ))}
  </div>
)

/* -------------------- 主组件 -------------------- */
const NoteForm = () => {
  const navigate = useNavigate();
  /* ---- 全局状态 ---- */
  const { addPendingTask, currentTaskId, setCurrentTask, getCurrentTask, updateTaskContent } =
    useTaskStore()
  const { loadEnabledModels, modelList } = useModelStore()

  /* ---- 表单 ---- */
  const form = useForm<NoteFormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: createEmptyFormValues(modelList[0]?.model_name || ''),
  })
  const currentTask = getCurrentTask()

  /* ---- 派生状态（只 watch 一次，提高性能） ---- */
  const videoUnderstandingEnabled = useWatch({ control: form.control, name: 'video_understanding' })
  const selectedModelName = useWatch({ control: form.control, name: 'model_name' })
  const selectedProviderId = useWatch({ control: form.control, name: 'provider_id' })
  const editing = currentTask && currentTask.id
  const [showNoteOptions, setShowNoteOptions] = useState(false)
  const [uploadingPaper, setUploadingPaper] = useState(false)
  const [submissionMode, setSubmissionMode] = useState<'paper_url' | 'verification'>('paper_url')
  const isPaperTask = currentTask?.platform === 'paper' || currentTask?.formData?.input_mode === 'paper'
  const selectedModelId = modelList.find(
    item => item.provider_id === selectedProviderId && item.model_name === selectedModelName,
  )?.id || ''

  const goModelAdd = () => {
    navigate("/settings/model");
  };
  /* ---- 副作用 ---- */
  useEffect(() => {
    loadEnabledModels()

    return
  }, [loadEnabledModels])
  useEffect(() => {
    const task = getCurrentTask()
    if (!task) {
      form.reset(createEmptyFormValues())
      setSubmissionMode('paper_url')
      return
    }
    const { formData } = task
    const reportModel = task.insights?.reading_report?.model

    form.reset({
      platform: ['douyin', 'bilibili', 'kuaishou'].includes(formData.platform)
        ? formData.platform as 'douyin' | 'bilibili' | 'kuaishou'
        : 'douyin',
      video_url: formData.video_url || '',
      model_name: formData.model_name || reportModel?.model_name || '',
      provider_id: formData.provider_id || reportModel?.provider_id || '',
      style: formData.style || 'minimal',
      quality: formData.quality || 'medium',
      extras: formData.extras || '',
      collection_folder: formData.collection_folder || task.collection?.folder || '核验历史',
      collection_tags: formData.collection_tags || task.collection?.tags?.join('，') || '',
      collection_note: formData.collection_note || task.collection?.note || '',
      screenshot: formData.screenshot ?? false,
      link: formData.link ?? false,
      video_understanding: formData.video_understanding ?? false,
      video_interval: formData.video_interval ?? 6,
      grid_size: formData.grid_size ?? [2, 2],
      format: formData.format ?? [],
    })
    setSubmissionMode(formData.input_mode === 'paper' || task.platform === 'paper' ? 'paper_url' : 'verification')
  }, [currentTaskId, form, getCurrentTask])

  useEffect(() => {
    const defaultModel = modelList[0]
    if (currentTaskId || !defaultModel) return
    if (form.getValues('model_name') || form.getValues('provider_id')) return
    form.setValue('model_name', defaultModel.model_name)
    form.setValue('provider_id', defaultModel.provider_id)
  }, [currentTaskId, form, modelList])

  /* ---- 帮助函数 ---- */
  const isGenerating = () => !['SUCCESS', 'FAILED', undefined].includes(getCurrentTask()?.status)
  const generating = isGenerating()
  const registerPaperSnapshot = (
    snapshot: TaskSnapshot,
    values: NoteFormValues,
    sourceLabel: string,
  ) => {
    const taskId = snapshot.id
    addPendingTask(taskId, 'paper', {
      ...values,
      video_url: sourceLabel,
      platform: 'paper',
      input_mode: 'paper',
    })
    updateTaskContent(taskId, {
      status: snapshot.status,
      message: snapshot.message,
      transcript: snapshot.result?.transcript || snapshot.transcript,
      audioMeta: snapshot.result?.audioMeta || snapshot.audioMeta,
      insights: snapshot.result?.insights || snapshot.insights,
    })
    setCurrentTask(taskId)
    window.dispatchEvent(new CustomEvent('reelmind:workspace-command', {
      detail: { viewMode: 'report', chat: false },
    }))
  }
  const handlePaperUpload = async (file?: File) => {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      toast.error('当前仅支持 PDF 论文')
      return
    }
    const values = form.getValues()
    const model = modelList.find(
      item => item.provider_id === values.provider_id && item.model_name === values.model_name,
    )
    if (!model) {
      toast.error('请先选择一个可用的模型与供应商')
      return
    }
    const paperValues = {
      ...values,
      provider_id: model.provider_id,
      model_name: model.model_name,
    }
    setUploadingPaper(true)
    try {
      const snapshot = await ingest_paper_pdf({
        file,
        provider_id: model.provider_id,
        model_name: model.model_name,
      })
      registerPaperSnapshot(snapshot, paperValues, file.name)
      toast.success('PDF 已导入，可一键生成阅读报告')
    }
    catch (error) {
      console.error('论文 PDF 导入失败', error)
      toast.error('论文 PDF 导入失败，请检查文件是否可解析')
    }
    finally {
      setUploadingPaper(false)
    }
  }
  const onSubmit = async (values: NoteFormValues) => {
    const rawInput = values.video_url?.trim() || ''
    const provider = modelList.find(
      item => item.provider_id === values.provider_id && item.model_name === values.model_name,
    )
    if (!provider) {
      toast.error('请选择一个可用的模型与供应商')
      return
    }
    if (isPaperTask) {
      window.dispatchEvent(new CustomEvent('reelmind:workspace-command', {
        detail: { viewMode: 'report', chat: false },
      }))
      return
    }
    const payload = {
      ...values,
      provider_id: provider.provider_id,
      task_id: currentTaskId || '',
      verification_depth: 'deep',
      source_policy: 'authoritative',
      input_mode: isHttpUrl(rawInput) ? 'url' : 'text',
    }
    if (!currentTaskId && submissionMode === 'paper_url') {
      if (!isHttpUrl(rawInput)) {
        toast.error('论文 URL 模式需要输入可访问的 http(s) 论文或 PDF 链接')
        return
      }
      try {
        const paperUrl = extractFirstUrl(rawInput)
        const snapshot = await ingest_paper_url({
          url: paperUrl,
          provider_id: provider.provider_id,
          model_name: provider.model_name,
        })
        registerPaperSnapshot(snapshot, {
          ...values,
          provider_id: provider.provider_id,
          model_name: provider.model_name,
        }, paperUrl)
        toast.success('论文 URL 已导入，可一键生成阅读报告')
      }
      catch (error) {
        console.error('论文 URL 导入失败', error)
        toast.error('论文 URL 导入失败，请确认链接可直接访问正文或 PDF')
      }
      return
    }
    if (currentTaskId) {
      const previousTask = getCurrentTask()
      updateTaskContent(currentTaskId, {
        status: 'SEARCHING_WEB',
        message: '重新联网核实中',
        error: undefined,
      })
      try {
        const snapshot = await rerun_verification_task(currentTaskId) as TaskSnapshot
        const insights = snapshot.result?.insights || snapshot.insights
        const nextTask = {
          status: snapshot.status,
          message: snapshot.message,
          error: snapshot.error,
        }
        updateTaskContent(currentTaskId, insights ? { ...nextTask, insights } : nextTask)
      }
      catch (error) {
        updateTaskContent(currentTaskId, {
          status: previousTask?.status || 'SUCCESS',
          message: previousTask?.message,
          error: previousTask?.error,
        })
        throw error
      }
      return
    }

    const data = await create_verification_task({
      url: isHttpUrl(rawInput) ? extractFirstUrl(rawInput) : '',
      text: isHttpUrl(rawInput) ? '' : rawInput,
      max_claims: 50,
      verification_depth: 'deep',
      source_policy: 'authoritative',
      model_name: values.model_name,
      provider_id: provider.provider_id,
    })
    addPendingTask(data.task_id, 'verification', payload)
  }
  const onInvalid = (errors: FieldErrors<NoteFormValues>) => {
    console.warn('表单校验失败：', errors)
    // message.error('请完善所有必填项后再提交')
  }
  const handleCreateNew = () => {
    // 🔁 这里清空当前任务状态
    // 比如调用 resetCurrentTask() 或者 navigate 到一个新页面
    setCurrentTask(null)
  }

  /* -------------------- 渲染 -------------------- */
  return (
    <div className="h-full w-full">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit, onInvalid)} className="space-y-4">
          <div className="grid grid-cols-2 gap-1 rounded-md bg-slate-100 p-1">
            <button
              type="button"
              disabled={Boolean(editing)}
              onClick={() => setSubmissionMode('paper_url')}
              className={`inline-flex h-8 items-center justify-center gap-1.5 rounded-sm px-2 text-xs font-semibold transition ${
                submissionMode === 'paper_url'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-800'
              } disabled:cursor-not-allowed`}
            >
              <BookOpenCheck className="h-3.5 w-3.5" />
              论文 URL
            </button>
            <button
              type="button"
              disabled={Boolean(editing)}
              onClick={() => setSubmissionMode('verification')}
              className={`inline-flex h-8 items-center justify-center gap-1.5 rounded-sm px-2 text-xs font-semibold transition ${
                submissionMode === 'verification'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-800'
              } disabled:cursor-not-allowed`}
            >
              <SearchCheck className="h-3.5 w-3.5" />
              文本 / 网页核实
            </button>
          </div>

          <div className="rounded-md border border-blue-200 bg-blue-50/70 p-3">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-blue-600 text-white">
                <FileUp className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-blue-950">优先导入论文 PDF</div>
                <p className="mt-0.5 text-xs leading-5 text-blue-800">
                  保留分页正文，阅读报告和持续追问才能给出页码引用。
                </p>
                <label className={`mt-2 inline-flex h-8 cursor-pointer items-center rounded-md border border-blue-300 bg-white px-3 text-xs font-semibold text-blue-800 transition hover:bg-blue-100 ${uploadingPaper ? 'pointer-events-none opacity-60' : ''}`}>
                  {uploadingPaper ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <FileUp className="mr-1.5 h-3.5 w-3.5" />}
                  {uploadingPaper ? '正在解析 PDF…' : '选择 PDF 并导入'}
                  <input
                    type="file"
                    accept="application/pdf,.pdf"
                    className="hidden"
                    disabled={uploadingPaper}
                    onChange={event => {
                      const file = event.target.files?.[0]
                      event.target.value = ''
                      handlePaperUpload(file)
                    }}
                  />
                </label>
              </div>
            </div>
          </div>

          {/* 主行动：论文导入或联网核实 */}
          {isPaperTask ? (
            <button
              type="button"
              onClick={() => window.dispatchEvent(new CustomEvent('reelmind:workspace-command', {
                detail: { viewMode: 'report', chat: false },
              }))}
              className="flex h-10 w-full items-center justify-center gap-2 rounded-md border border-blue-200 bg-blue-50 px-4 text-sm font-semibold text-blue-900 transition hover:bg-blue-100"
            >
              <BookOpenCheck className="h-4 w-4" />
              前往阅读报告
            </button>
          ) : <div className="space-y-2">
            <div className={editing ? 'grid grid-cols-[minmax(0,1fr)_112px] gap-2' : ''}>
              <button
                type="submit"
                disabled={generating || uploadingPaper}
                className="group flex h-10 w-full cursor-pointer items-center justify-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {generating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <SearchCheck className="h-4 w-4" />
                )}
                <span className="truncate">
                  {generating
                    ? '正在核实…'
                    : editing
                      ? '重新联网核实'
                      : submissionMode === 'paper_url'
                        ? '导入论文 URL'
                        : '开始联网核实'}
                </span>
              </button>
              {editing && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-10 whitespace-nowrap px-2 text-xs"
                  onClick={handleCreateNew}
                >
                  <Plus className="mr-1 h-3.5 w-3.5" />
                  新建
                </Button>
              )}
            </div>
            {generating && (
              <p className="font-mono text-[10px] leading-4 text-slate-400">
                深度核验将检索、抓取原文并交叉判定，耗时较长，请勿离开此页。
              </p>
            )}
          </div>}

          {/* 核实内容 */}
          <div>
            <SectionHeader
              title={submissionMode === 'paper_url' ? '论文 URL' : '核实内容'}
              tip={submissionMode === 'paper_url'
                ? '输入可直接访问的论文详情页或 PDF URL，系统会保留论文身份与分页正文'
                : '粘贴网页 URL 或直接输入一段待核实文本'}
            />
            <div>
              <FormField
                control={form.control}
                name="video_url"
                render={({ field }) => (
                  <FormItem>
                    <Textarea
                      disabled={!!editing}
                      placeholder={submissionMode === 'paper_url'
                        ? '输入论文详情页或 PDF URL，例如 https://example.org/paper.pdf'
                        : '输入网页 URL，或粘贴要联网核实的文本。长文本会被拆成 atomic claims 后逐条联网核验。'}
                      className="min-h-28 resize-y font-mono text-xs leading-5"
                      {...field}
                    />
                    <FormMessage style={{ display: 'none' }} />
                  </FormItem>
                )}
              />
            </div>
          </div>

          {/* 核验模型 */}
          <div>
            <SectionHeader title="阅读 / 核验模型" tip="模型与供应商共同确定，避免同名模型调用到错误供应商" />
            {modelList.length > 0 ? (
              <FormField
                control={form.control}
                name="model_name"
                render={({ field }) => (
                  <FormItem>
                      <Select
                        onOpenChange={open => {
                          if (open) loadEnabledModels()
                        }}
                        value={selectedModelId}
                        onValueChange={modelId => {
                          const model = modelList.find(item => item.id === modelId)
                          if (!model) return
                          field.onChange(model.model_name)
                          form.setValue('provider_id', model.provider_id)
                        }}
                    >
                      <FormControl>
                        <SelectTrigger className="w-full min-w-0 truncate">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {modelList.map(m => (
                          <SelectItem key={m.id} value={m.id}>
                            <div className="flex min-w-0 items-center gap-2">
                              <span className="truncate">{m.model_name}</span>
                              <span className="truncate font-mono text-[10px] text-slate-400">{m.provider_id}</span>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            ) : (
              <FormItem>
                <Button type="button" variant="outline" onClick={() => { goModelAdd() }}>
                  请先添加模型
                </Button>
                <FormMessage />
              </FormItem>
            )}
          </div>

          {/* 次级：辅助产物与视频专项（可折叠） */}
          <div className="rounded-md border border-slate-200">
            <button
              type="button"
              onClick={() => setShowNoteOptions(v => !v)}
              className="flex w-full cursor-pointer items-center justify-between px-3 py-2 text-left transition hover:bg-slate-50"
            >
              <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                辅助产物与视频专项
              </span>
              <ChevronDown
                className={`h-3.5 w-3.5 text-slate-400 transition-transform ${showNoteOptions ? 'rotate-180' : ''}`}
              />
            </button>

            {showNoteOptions && (
              <div className="space-y-4 border-t border-slate-200 px-3 py-3">
                {/* 辅助笔记风格 */}
                <FormField
                  control={form.control}
                  name="style"
                  render={({ field }) => (
                    <FormItem>
                      <SectionHeader title="辅助笔记风格" tip="仅影响次级笔记产物，不参与联网核实判定" />
                      <Select
                        value={field.value}
                        onValueChange={field.onChange}
                        defaultValue={field.value}
                      >
                        <FormControl>
                          <SelectTrigger className="w-full min-w-0 truncate">
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {noteStyles.map(({ label, value }) => (
                            <SelectItem key={value} value={value}>
                              {label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 辅助产物 */}
                <FormField
                  control={form.control}
                  name="format"
                  render={({ field }) => (
                    <FormItem>
                      <SectionHeader title="辅助产物" tip="核验报告始终生成；这里仅控制附带的阅读产物" />
                      <CheckboxGroup
                        value={field.value}
                        onChange={field.onChange}
                        disabledMap={{
                          link: false,
                          screenshot: !videoUnderstandingEnabled,
                        }}
                      />
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 归档信息 */}
                <div>
                  <SectionHeader title="归档信息" tip="用于在核验历史里分类和检索" />
                  <div className="space-y-2">
                    <FormField
                      control={form.control}
                      name="collection_folder"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel className="text-xs text-slate-600">归档目录</FormLabel>
                          <Input placeholder="核验历史" {...field} />
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="collection_tags"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel className="text-xs text-slate-600">标签</FormLabel>
                          <Input placeholder="经济学，商业思维" {...field} />
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="collection_note"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel className="text-xs text-slate-600">收藏备注</FormLabel>
                          <Textarea placeholder="为什么收藏、后续复习重点…" {...field} />
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </div>

                {/* 视频理解 */}
                <div>
                  <SectionHeader title="视频与平台诊断" tip="仅在输入抖音/B站/快手视频时使用；普通网页和文本核验不依赖这里" />
                  <div className="flex flex-col gap-2">
                    <FormField
                      control={form.control}
                      name="platform"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel className="text-xs text-slate-600">视频平台</FormLabel>
                          <Select
                            disabled={!!editing}
                            value={field.value}
                            onValueChange={field.onChange}
                            defaultValue={field.value}
                          >
                            <FormControl>
                              <SelectTrigger className="w-full">
                                <SelectValue />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {videoPlatforms?.map(p => (
                                <SelectItem key={p.value} value={p.value}>
                                  <div className="flex items-center justify-center gap-2">
                                    <div className="h-4 w-4">{p.logo()}</div>
                                    <span>{p.label}</span>
                                  </div>
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="video_understanding"
                      render={() => (
                        <FormItem>
                          <div className="flex items-center gap-2">
                            <FormLabel className="text-xs text-slate-600">启用</FormLabel>
                            <Checkbox
                              checked={videoUnderstandingEnabled}
                              onCheckedChange={v => form.setValue('video_understanding', v)}
                            />
                          </div>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <div className="grid grid-cols-2 gap-3">
                      {/* 采样间隔 */}
                      <FormField
                        control={form.control}
                        name="video_interval"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel className="text-xs text-slate-600">采样间隔（秒）</FormLabel>
                            <Input disabled={!videoUnderstandingEnabled} type="number" {...field} />
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      {/* 拼图大小 */}
                      <FormField
                        control={form.control}
                        name="grid_size"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel className="text-xs text-slate-600">拼图尺寸（列 × 行）</FormLabel>
                            <div className="flex items-center space-x-2">
                              <Input
                                disabled={!videoUnderstandingEnabled}
                                type="number"
                                value={field.value?.[0] || 3}
                                onChange={e => field.onChange([+e.target.value, field.value?.[1] || 3])}
                                className="w-16"
                              />
                              <span className="text-slate-400">×</span>
                              <Input
                                disabled={!videoUnderstandingEnabled}
                                type="number"
                                value={field.value?.[1] || 3}
                                onChange={e => field.onChange([field.value?.[0] || 3, +e.target.value])}
                                className="w-16"
                              />
                            </div>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                    <Alert variant="warning" className="text-xs">
                      <AlertDescription>
                        <strong>提示：</strong>视频理解功能必须使用多模态模型。
                      </AlertDescription>
                    </Alert>
                  </div>
                </div>

                {/* 备注 */}
                <FormField
                  control={form.control}
                  name="extras"
                  render={({ field }) => (
                    <FormItem>
                      <SectionHeader title="备注" tip="可在 Prompt 结尾附加自定义说明" />
                      <Textarea placeholder="笔记需要罗列出 xxx 关键点…" {...field} />
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            )}
          </div>
        </form>
      </Form>
    </div>
  )
}

export default NoteForm
