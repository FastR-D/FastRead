import request from '@/utils/request'
import toast from 'react-hot-toast'
import type {
  AudioMeta,
  CollectionMeta,
  Markdown,
  NoteInsights,
  TaskFailure,
  PaperDocument,
  TaskStatus,
  Transcript,
  ReadingReport,
} from '@/store/taskStore'

type BackendTaskResult = {
  markdown?: string | Markdown[]
  transcript?: unknown
  audio_meta?: unknown
  audioMeta?: unknown
  insights?: NoteInsights
  paper_input?: PaperInput
  paper_document?: PaperDocument
  verification_input?: VerificationInput
}

export type PaperInput = {
  source_url?: string
  filename?: string
  provider_id?: string
  model_name?: string
}

export type VerificationInput = {
  input_mode?: 'text' | 'url'
  text?: string
  url?: string
  provider_id?: string
  model_name?: string
}

type BackendTaskSnapshot = {
  id?: string
  task_id?: string
  status?: string
  message?: string
  error?: TaskFailure
  result?: BackendTaskResult | null
  markdown?: string | Markdown[]
  insights?: NoteInsights
  audio_meta?: unknown
  audioMeta?: unknown
  transcript?: unknown
  createdAt?: string | number
  updatedAt?: string | number
  videoUrl?: string
  collection?: CollectionMeta | null
  title?: string
  coverUrl?: string
}

export type TaskSnapshotResult = {
  markdown?: string | Markdown[]
  transcript?: Transcript
  audioMeta?: AudioMeta
  insights?: NoteInsights
  paperInput?: PaperInput
  paperDocument?: PaperDocument
  verificationInput?: VerificationInput
}

export type TaskSnapshot = {
  id: string
  taskId: string
  status: TaskStatus
  message?: string
  error?: TaskFailure
  result?: TaskSnapshotResult
  markdown?: string | Markdown[]
  insights?: NoteInsights
  audioMeta?: AudioMeta
  transcript?: Transcript
  createdAt?: string
  updatedAt?: string
  videoUrl?: string
  collection?: CollectionMeta | null
  title?: string
  coverUrl?: string
}

const isRecord = (value: unknown): value is Record<string, any> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const normalizeTimestamp = (value: unknown): string | undefined => {
  if (value === undefined || value === null || value === '') return undefined

  if (typeof value === 'number') {
    const milliseconds = value > 1_000_000_000_000 ? value : value * 1000
    const date = new Date(milliseconds)
    return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
  }

  if (typeof value === 'string') {
    const numericValue = Number(value)
    if (!Number.isNaN(numericValue) && value.trim() !== '') {
      return normalizeTimestamp(numericValue)
    }

    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
  }

  return undefined
}

const normalizeAudioMeta = (value: unknown): AudioMeta | undefined => {
  if (!isRecord(value)) return undefined

  return {
    cover_url: String(value.cover_url || ''),
    duration: Number(value.duration || 0),
    file_path: String(value.file_path || ''),
    platform: String(value.platform || ''),
    raw_info: value.raw_info ?? null,
    title: String(value.title || ''),
    video_id: String(value.video_id || ''),
  }
}

const normalizeTranscript = (value: unknown): Transcript | undefined => {
  if (!isRecord(value)) return undefined

  const segments = Array.isArray(value.segments)
    ? value.segments
        .filter(isRecord)
        .map(segment => ({
          start: Number(segment.start || 0),
          end: Number(segment.end || 0),
          text: String(segment.text || ''),
        }))
    : []

  return {
    full_text: String(value.full_text || ''),
    language: String(value.language || ''),
    raw: value.raw ?? null,
    segments,
  }
}

export const normalizeTaskSnapshot = (payload: unknown): TaskSnapshot | null => {
  if (!isRecord(payload)) return null

  const raw = payload as BackendTaskSnapshot
  const result = isRecord(raw.result) ? raw.result : undefined
  const audioMeta = normalizeAudioMeta(result?.audioMeta || result?.audio_meta || raw.audioMeta || raw.audio_meta)
  const transcript = normalizeTranscript(result?.transcript || raw.transcript)
  const markdown = raw.markdown ?? result?.markdown
  const insights = raw.insights ?? result?.insights
  const paperInput = result?.paper_input
  const paperDocument = result?.paper_document
  const verificationInput = result?.verification_input
  const taskId = String(raw.id || raw.task_id || '')

  return {
    id: taskId,
    taskId,
    status: String(raw.status || 'PENDING') as TaskStatus,
    message: raw.message,
    error: raw.error,
    result:
      result || markdown !== undefined || transcript || audioMeta || insights
        ? {
            markdown,
            transcript,
            audioMeta,
            insights,
            paperInput,
            paperDocument,
            verificationInput,
          }
        : undefined,
    markdown,
    insights,
    audioMeta,
    transcript,
    createdAt: normalizeTimestamp(raw.createdAt ?? (raw as any).created_at),
    updatedAt: normalizeTimestamp(raw.updatedAt ?? (raw as any).updated_at),
    videoUrl:
      raw.videoUrl ||
      paperInput?.source_url ||
      paperInput?.filename ||
      verificationInput?.url ||
      '',
    collection: raw.collection,
    title: raw.title,
    coverUrl: raw.coverUrl,
  }
}

export const generateNote = async (data: {
  video_url: string
  platform: string
  quality: string
  model_name: string
  provider_id: string
  task_id?: string
  format: Array<string>
  style: string
  extras?: string
  collection_folder?: string
  collection_tags?: string
  collection_note?: string
  video_understand?: boolean
  video_interval?: number
  grid_size: Array<number>
}) => {
  try {
    console.log('generateNote', data)
    const response = await request.post('/generate_note', data)

    if (!response) {
      toast.error('笔记生成任务提交失败')
      return null
    }
    toast.success('笔记生成任务已提交！')

    console.log('res', response)
    // 成功提示

    return response
  } catch (e: any) {
    console.error('❌ 请求出错', e)

    // 错误提示
    // toast.error('笔记生成失败，请稍后重试')

    throw e // 抛出错误以便调用方处理
  }
}

export const delete_task = async ({
  task_id,
  video_id,
  platform,
}: {
  task_id?: string
  video_id?: string
  platform: string
}) => {
  try {
    const data = {
      task_id,
      video_id,
      platform,
    }
    const res = await request.post('/delete_task', data)


      toast.success('任务已成功删除')
      return res
  } catch (e) {
    toast.error('请求异常，删除任务失败')
    console.error('❌ 删除任务失败:', e)
    throw e
  }
}

export const update_task_collection = async (data: {
  task_id: string
  collection_folder: string
  collection_tags: string[]
  collection_note: string
}) => {
  return await request.post('/update_task_collection', data)
}

export const verify_task_online = async (data: {
  task_id: string
  max_claims?: number
  model_name?: string
  provider_id?: string
}) => {
  return await request.post('/verify_task_online', data, { timeout: 600000 })
}

export const create_verification_task = async (data: {
  text?: string
  url?: string
  task_id?: string
  max_claims?: number
  verification_depth?: string
  source_policy?: string
  model_name?: string
  provider_id?: string
}) => {
  return await request.post('/verification_tasks', {
    goal: 'verify',
    verification_depth: 'deep',
    source_policy: 'authoritative',
    max_claims: 50,
    ...data,
  }, { timeout: 600000 })
}

export const rerun_verification_task = async (task_id: string, retry_failed_only = true) => {
  return await request.post(`/verification_tasks/${task_id}/rerun`, { retry_failed_only }, { timeout: 600000 })
}

export const rerun_verification_claim = async (task_id: string, claim_id: string) => {
  return await request.post(`/verification_tasks/${task_id}/claims/${claim_id}/rerun`, {}, { timeout: 600000 })
}

export const generate_reading_report = async (data: {
  task_id: string
  provider_id: string
  model_name: string
  force?: boolean
}): Promise<{ task_id: string; reading_report: ReadingReport }> => {
  return await request.post('/reading_reports', data, { timeout: 180000 }) as any
}

export const save_personal_summary = async (taskId: string, summary: string): Promise<{
  task_id: string
  personal_summary: { content: string; updated_at: string; max_chars: number }
}> => {
  return await request.put(`/reading_reports/${taskId}/personal_summary`, { summary }) as any
}

export const ingest_paper_pdf = async (data: {
  file: File
  provider_id?: string
  model_name?: string
  source_url?: string
  venue?: string
  doi?: string
  year?: string
}): Promise<TaskSnapshot> => {
  const body = new FormData()
  body.append('file', data.file)
  body.append('provider_id', data.provider_id || '')
  body.append('model_name', data.model_name || '')
  body.append('source_url', data.source_url || '')
  body.append('venue', data.venue || '')
  body.append('doi', data.doi || '')
  body.append('year', data.year || '')
  const snapshot = normalizeTaskSnapshot(
    await request.post('/papers/upload', body, { timeout: 180000 }),
  )
  if (!snapshot) throw new Error('论文导入响应格式异常')
  return snapshot
}

export const ingest_paper_url = async (data: {
  url: string
  provider_id?: string
  model_name?: string
  title?: string
  authors?: string[]
  venue?: string
  doi?: string
  year?: number
}): Promise<TaskSnapshot> => {
  const snapshot = normalizeTaskSnapshot(
    await request.post('/papers/from_url', data, { timeout: 180000 }),
  )
  if (!snapshot) throw new Error('论文 URL 导入响应格式异常')
  return snapshot
}

export const resolve_backend_resource_url = (value?: string | null): string => {
  const resource = String(value || '').trim()
  if (!resource) return ''
  if (/^(?:https?:|data:|blob:)/i.test(resource)) return resource

  const path = resource.startsWith('/') ? resource : `/${resource}`
  const apiBase = String(import.meta.env.VITE_API_BASE_URL || '/api').trim()
  if (/^https?:\/\//i.test(apiBase)) {
    try {
      return new URL(path, new URL(apiBase).origin).toString()
    }
    catch {
      return path
    }
  }
  return path
}

export const get_task_status = async (task_id: string): Promise<TaskSnapshot> => {
  try {
    // 成功提示

    const snapshot = normalizeTaskSnapshot(await request.get('/task_status/' + task_id, { silent: true }))
    if (!snapshot) {
      throw new Error('任务状态响应格式异常')
    }
    return snapshot
  } catch (e) {
    console.warn('任务状态轮询请求失败，交由轮询器重试', e)
    throw e
  }
}

export const list_generated_tasks = async (): Promise<TaskSnapshot[]> => {
  try {
    const tasks = await request.get('/tasks')
    if (!Array.isArray(tasks)) return []
    return tasks.map(normalizeTaskSnapshot).filter((task): task is TaskSnapshot => Boolean(task?.id))
  } catch (e) {
    console.error('❌ 获取知识卡片列表失败:', e)
    throw e
  }
}
