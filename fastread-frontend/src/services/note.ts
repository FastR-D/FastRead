import request from '@/utils/request'
import type {
  AcademicGate,
  CollectionMeta,
  NoteInsights,
  PaperDocument,
  ReadingReport,
  TaskFailure,
  TaskStatus,
} from '@/store/taskStore'

export type PaperInput = {
  source_url?: string
  filename?: string
  provider_id?: string
  model_name?: string
}

export type TaskSnapshot = {
  id: string
  taskId: string
  kind: 'paper'
  status: TaskStatus
  title: string
  message?: string
  error?: TaskFailure
  paperDocument?: PaperDocument
  insights?: NoteInsights
  readingReport?: ReadingReport
  personalSummary?: NoteInsights['personal_summary']
  collection: CollectionMeta
  paperInput: PaperInput
  createdAt?: string
  updatedAt?: string
}

const DEFAULT_COLLECTION: CollectionMeta = {
  folder: '默认收藏夹',
  tags: [],
  note: '',
}

const isRecord = (value: unknown): value is Record<string, any> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const normalizeTimestamp = (value: unknown): string | undefined => {
  if (value === undefined || value === null || value === '') return undefined
  if (typeof value === 'number') {
    const date = new Date(value > 1_000_000_000_000 ? value : value * 1000)
    return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
  }
  const date = new Date(String(value))
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
}

export const normalizeTaskSnapshot = (payload: unknown): TaskSnapshot | null => {
  if (!isRecord(payload)) return null
  const taskId = String(payload.id || payload.task_id || '')
  if (!taskId || payload.kind !== 'paper') return null

  const result = isRecord(payload.result) ? payload.result : {}
  const document = (payload.paperDocument || result.paper_document) as PaperDocument | undefined
  if (!document && payload.status === 'SUCCESS') return null
  const insights = (result.insights || payload.insights || {}) as NoteInsights
  const readingReport = (payload.readingReport || insights.reading_report) as ReadingReport | undefined
  const personalSummary = payload.personalSummary || insights.personal_summary
  const collection = isRecord(payload.collection)
    ? {
        folder: String(payload.collection.folder || DEFAULT_COLLECTION.folder),
        tags: Array.isArray(payload.collection.tags)
          ? payload.collection.tags.map(String).filter(Boolean)
          : [],
        note: String(payload.collection.note || ''),
      }
    : DEFAULT_COLLECTION
  const reportModel = readingReport?.model

  return {
    id: taskId,
    taskId,
    kind: 'paper',
    status: String(payload.status || 'PENDING') as TaskStatus,
    title: String(payload.title || document?.title || '未命名论文'),
    message: payload.message ? String(payload.message) : undefined,
    error: isRecord(payload.error) ? payload.error as TaskFailure : undefined,
    paperDocument: document,
    insights: {
      ...insights,
      ...(readingReport ? { reading_report: readingReport } : {}),
      ...(personalSummary ? { personal_summary: personalSummary } : {}),
    },
    readingReport,
    personalSummary,
    collection,
    paperInput: {
      source_url: String(document?.source_url || ''),
      filename: String(document?.filename || ''),
      provider_id: String(reportModel?.provider_id || ''),
      model_name: String(reportModel?.model_name || ''),
    },
    createdAt: normalizeTimestamp(payload.createdAt ?? payload.created_at),
    updatedAt: normalizeTimestamp(payload.updatedAt ?? payload.updated_at),
  }
}

export const delete_paper = async (taskId: string) =>
  request.delete(`/papers/${encodeURIComponent(taskId)}`)

export const update_task_collection = async (data: {
  task_id: string
  collection_folder: string
  collection_tags: string[]
  collection_note: string
}) => request.put(`/papers/${encodeURIComponent(data.task_id)}/collection`, {
  collection_folder: data.collection_folder,
  collection_tags: data.collection_tags,
  collection_note: data.collection_note,
})

export const delete_collection_folder = async (folder: string): Promise<{
  collection_folder: string
  replacement_folder: string
  updated_task_ids: string[]
  updated_count: number
}> => request.delete('/collections', { params: { collection_folder: folder } }) as any

export type SearchTrack = 'security' | 'systems' | 'ai'

export type SearchVenue = {
  id: string
  name: string
  short_name: string
  track: SearchTrack | string
}

export type PaperSearchResult = {
  id: string
  title: string
  abstract: string
  authors: string[]
  categories: string[]
  comment: string
  journal_ref: string
  doi: string
  year: number | null
  published_at: string
  source_url: string
  pdf_url: string
  source: 'arxiv' | 'google_scholar' | string
  keywords: string[]
  keyword_strategy: 'ai_enriched' | 'deterministic_fallback' | string
  venue: SearchVenue & { raw?: string }
  venue_confirmed: boolean
  track: SearchTrack | ''
  scope_tier: 'core' | 'arxiv' | 'scholar'
  scope_label: string
  evidence_status: 'discovery_metadata' | 'full_text_imported' | string
  full_text_verified: boolean
  relevance: number
  cited_by?: number | null
  provenance: {
    provider: string
    retrieved_at: string
    metadata_only: boolean
    note: string
  }
}

export type ProviderHealth = {
  configured?: boolean
  available: boolean
  reason?: string
  error?: string
  provider?: string
  result_count?: number
  status?: string
  manual_search_url?: string
  http_status?: number
  query_count?: number
  via_proxy?: boolean
}

export type PaperSearchResponse = {
  query: string
  semantic_queries?: string[]
  tracks: SearchTrack[]
  search_backend: string
  search_backend_error?: string
  elasticsearch_available: boolean
  provider_status: Record<string, ProviderHealth>
  network_policy?: {
    academic_proxy_required: boolean
    academic_proxy_configured: boolean
    public_direct_allowed: boolean
    elasticsearch_uses_academic_proxy: boolean
  }
  venue_allowlist: SearchVenue[]
  results: PaperSearchResult[]
  result_count: number
  scope_counts: { core: number; arxiv: number; scholar: number }
  core_result_count: number
  venue_unconfirmed_count: number
  venue_unconfirmed: PaperSearchResult[]
  fetched_this_run: number
  index_stats: { documents: number; terms: number; last_indexed_at?: string }
  index_updated_at: string
  retrieved_at: string
  index_stale: boolean
  stale_after_hours: number
  keyword_extraction: {
    mode: string
    ai_configured: boolean
    job_id?: string
    prompt_version?: string
    strategy_version?: string
    status?: string
  }
  corpus_scope: {
    tracks: SearchTrack[]
    core_venues: SearchVenue[]
    sources: string[]
    evidence_boundary: string
  }
  coverage_note: string
}

export const search_papers = async (data: {
  query: string
  tracks?: SearchTrack[]
  venue_ids?: string[]
  limit?: number
  include_unconfirmed?: boolean
  refresh?: boolean
  include_arxiv?: boolean
  include_scholar?: boolean
  include_crossref?: boolean
  include_openalex?: boolean
  include_semantic_scholar?: boolean
}): Promise<PaperSearchResponse> => request.post('/papers/search', data, { timeout: 12000 }) as any

export const list_search_venues = async (): Promise<{ venues: SearchVenue[] }> =>
  request.get('/papers/search/venues') as any

export type PaperIndexJob = {
  job_id: string
  status: 'running' | 'completed' | 'completed_with_fallback' | 'failed' | string
  provider_id: string
  model_name: string
  prompt_version: string
  strategy_version: string
  corpus_count: number
  ai_keyword_count: number
  fallback_count: number
  fallback_reasons: Record<string, number>
  local_index_count: number
  elasticsearch_index_count: number
  search_backend: 'elasticsearch' | 'local_inverted_index' | string
  error: string
  started_at: string
  completed_at: string
}

export const rebuild_paper_index = async (data: {
  provider_id: string
  model_name: string
  use_ai?: boolean
}): Promise<PaperIndexJob> => request.post('/papers/search/index/rebuild', data, { timeout: 600000 }) as any

export const get_paper_index_status = async (): Promise<PaperIndexJob | null> =>
  request.get('/papers/search/index/status') as any

export const generate_reading_report = async (data: {
  task_id: string
  provider_id: string
  model_name: string
  force?: boolean
}): Promise<{ task_id: string; reading_report: ReadingReport }> =>
  request.post('/reading_reports', data, { timeout: 600000 }) as any

export const save_personal_summary = async (taskId: string, summary: string): Promise<{
  task_id: string
  personal_summary: { content: string; updated_at: string; max_chars: number }
}> => request.put(`/reading_reports/${encodeURIComponent(taskId)}/personal_summary`, { summary }) as any

export const PERSONAL_SUMMARY_MAX_CHARS = 20_000

export const get_reading_report_markdown_url = (taskId: string): string =>
  resolve_backend_resource_url(`/api/reading_reports/${encodeURIComponent(taskId)}/export.md`)

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
  const snapshot = normalizeTaskSnapshot(await request.post('/papers/upload', body, { timeout: 180000 }))
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
  const snapshot = normalizeTaskSnapshot(await request.post('/papers/from_url', data, { timeout: 180000 }))
  if (!snapshot) throw new Error('论文 URL 导入响应格式异常')
  return snapshot
}

export const resolve_backend_resource_url = (value?: string | null): string => {
  const resource = String(value || '').trim()
  if (!resource) return ''
  if (/^(?:https?:|data:|blob:)/i.test(resource)) return resource
  const path = resource.startsWith('/') ? resource : `/${resource}`
  const apiBase = String(import.meta.env.VITE_API_BASE_URL || '/api').trim()
  if (!/^https?:\/\//i.test(apiBase)) return path
  try {
    return new URL(path, new URL(apiBase).origin).toString()
  }
  catch {
    return path
  }
}

export const get_task_status = async (taskId: string): Promise<TaskSnapshot> => {
  const snapshot = normalizeTaskSnapshot(
    await request.get(`/task_status/${encodeURIComponent(taskId)}`, { silent: true }),
  )
  if (!snapshot) throw new Error('论文任务状态响应格式异常')
  return snapshot
}

export const list_generated_tasks = async (): Promise<TaskSnapshot[]> => {
  const tasks = await request.get('/tasks')
  if (!Array.isArray(tasks)) return []
  return tasks.map(normalizeTaskSnapshot).filter((task): task is TaskSnapshot => Boolean(task))
}

export const academicGateFor = (document?: PaperDocument, insights?: NoteInsights): AcademicGate | undefined =>
  document?.academic_gate || insights?.academic_gate || insights?.reading_report?.academic_gate
