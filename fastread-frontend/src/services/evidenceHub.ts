import request from '@/utils/request'

export type PaperAnnotation = {
  id: string
  task_id: string
  page: number
  start_offset: number
  end_offset: number
  exact_quote: string
  note: string
  source_hash: string
  created_at: string
  updated_at: string
}

export type PaperCandidate = {
  id: string
  title: string
  authors: string[]
  year?: number | null
  venue: string
  abstract: string
  doi: string
  arxiv_id: string
  detail_url: string
  canonical_url: string
  pdf_url: string
  producer: 'fastnews' | 'fastinsight' | 'manual'
  source_commit: string
  fetched_at: string
  warnings: string[]
  categories: string[]
  match_score?: number | null
  import_status: 'pending' | 'imported'
  task_id?: string | null
  discovery_status: string
  source_lock_status: string
  deduplicated?: boolean
}

export type FastNewsEntry = Omit<PaperCandidate, 'id' | 'import_status' | 'source_lock_status'> & {
  catalog_id: string
  source_path: string
  source_line: number
}

export type TopicEvidenceItem = {
  id: string
  topic_id: string
  task_id: string
  page: number
  exact_quote: string
  user_note: string
  role: 'question' | 'method' | 'experiment' | 'limitation' | 'other'
  source_kind: 'manual' | 'annotation' | 'report' | 'model_classified'
  source_ref: string
}

export type EvidenceExtractionRun = {
  run_id: string
  topic_id: string
  task_id: string
  title: string
  status: 'completed' | 'completed_no_selection' | 'failed'
  provider_id: string
  model_name: string
  prompt_version: string
  strategy_version: string
  candidate_count: number
  selected_count: number
  selected_by_role: Record<TopicEvidenceItem['role'], number>
  unresolved_roles: TopicEvidenceItem['role'][]
  fallback_used: boolean
  fallback_reason: string
  error?: string
  generated_at: string
}

export type ResearchTopic = {
  id: string
  question: string
  scope_statement: string
  user_hypotheses: string[]
  paper_count?: number
  evidence_count?: number
  papers?: Array<{ task_id: string; title?: string; added_at: string; missing?: boolean }>
  evidence_items?: TopicEvidenceItem[]
  evidence_matrix?: Record<string, TopicEvidenceItem[]>
  evidence_extraction_runs?: EvidenceExtractionRun[]
  created_at: string
  updated_at: string
}

export type TopicSynthesisClaim = {
  statement: string
  citations: Array<{ task_id: string; page: number; exact_quote: string }>
}

export type TopicSynthesis = {
  id: string
  topic_id: string
  generated_at: string
  question: string
  kind: 'model' | 'manual'
  model?: { provider_id: string; model_name: string }
  common_reports: TopicSynthesisClaim[]
  differences: TopicSynthesisClaim[]
  conflicts: TopicSynthesisClaim[]
  evidence_gaps: string[]
  user_hypotheses: string[]
  idea_feasibility: {
    problem: string
    what_papers_achieved: TopicSynthesisClaim[]
    unsupported_hypotheses: string[]
    counterexamples_and_limitations: TopicSynthesisClaim[]
    minimum_validation_experiment: string
    evidence_to_read: string[]
  }
}

export type TopicAnswerSource = {
  source_id: string
  task_id: string
  title: string
  page_start: number
  page_end: number
  exact_quote: string
  text: string
  source_type: 'paper_page'
  source_url: string
  doi: string
}

export type TopicAnswer = {
  answer: string
  sources: TopicAnswerSource[]
  grounding_status: 'source_grounded' | 'insufficient'
}

export type FastWriteHandoff = {
  id: string
  bundle_id: string
  project_id: string
  status: 'pending' | 'writing' | 'completed' | 'failed' | 'conflict'
  target_path: string
  files: string[]
  successful_files: string[]
  error: string
  manifest_hash: string
  created_at: string
  updated_at: string
}

export const listAnnotations = (taskId: string): Promise<PaperAnnotation[]> =>
  request.get(`/papers/${taskId}/annotations`) as any

export const createAnnotation = (
  taskId: string,
  data: Pick<PaperAnnotation, 'page' | 'start_offset' | 'end_offset' | 'exact_quote' | 'note'>,
): Promise<PaperAnnotation> => request.post(`/papers/${taskId}/annotations`, data) as any

export const updateAnnotation = (
  taskId: string,
  annotationId: string,
  data: Partial<Pick<PaperAnnotation, 'page' | 'start_offset' | 'end_offset' | 'exact_quote' | 'note'>>,
): Promise<PaperAnnotation> => request.patch(`/papers/${taskId}/annotations/${annotationId}`, data) as any

export const deleteAnnotation = (taskId: string, annotationId: string) =>
  request.delete(`/papers/${taskId}/annotations/${annotationId}`)

export const getFastNewsCatalog = (params?: Record<string, unknown>): Promise<{
  repository: string
  commit: string
  updated_at: string
  stale: boolean
  warning?: string
  total: number
  entries: FastNewsEntry[]
}> => request.get('/integrations/fastnews/catalog', { params, timeout: 60000 }) as any

export const importFastNews = (catalogIds: string[]): Promise<PaperCandidate[]> =>
  request.post('/integrations/imports/fastnews', { catalog_ids: catalogIds }, { timeout: 60000 }) as any

export const importFastInsight = (payload: string): Promise<PaperCandidate[]> =>
  request.post('/integrations/imports/fastinsight', payload, {
    headers: { 'Content-Type': 'application/json' },
  }) as any

export const listImports = (params?: Record<string, unknown>): Promise<PaperCandidate[]> =>
  request.get('/integrations/imports', { params }) as any

export const confirmImport = (candidateId: string): Promise<PaperCandidate> =>
  request.post(`/integrations/imports/${candidateId}/confirm`, {}, { timeout: 180000 }) as any

export const deleteImport = (candidateId: string) => request.delete(`/integrations/imports/${candidateId}`)

export const createTopic = (data: {
  question: string
  scope_statement?: string
  user_hypotheses?: string[]
}): Promise<ResearchTopic> => request.post('/research_topics', data) as any

export const listTopics = (): Promise<ResearchTopic[]> => request.get('/research_topics') as any
export const getTopic = (topicId: string): Promise<ResearchTopic> => request.get(`/research_topics/${topicId}`) as any
export const updateTopic = (topicId: string, data: Partial<Pick<ResearchTopic, 'question' | 'scope_statement' | 'user_hypotheses'>>): Promise<ResearchTopic> =>
  request.patch(`/research_topics/${topicId}`, data) as any
export const deleteTopic = (topicId: string) => request.delete(`/research_topics/${topicId}`)
export const addTopicPaper = (topicId: string, taskId: string) => request.post(`/research_topics/${topicId}/papers/${taskId}`)
export const removeTopicPaper = (topicId: string, taskId: string) => request.delete(`/research_topics/${topicId}/papers/${taskId}`)
export const addTopicEvidence = (topicId: string, data: Omit<TopicEvidenceItem, 'id' | 'topic_id' | 'source_kind' | 'source_ref'>): Promise<TopicEvidenceItem> =>
  request.post(`/research_topics/${topicId}/evidence`, data) as any
export const deleteTopicEvidence = (topicId: string, evidenceId: string) => request.delete(`/research_topics/${topicId}/evidence/${evidenceId}`)
export const extractTopicEvidence = (topicId: string, data: {
  provider_id: string
  model_name: string
  max_candidates: 80 | 120 | 160
}): Promise<{ topic: ResearchTopic; runs: EvidenceExtractionRun[] }> =>
  request.post(`/research_topics/${topicId}/evidence/extract`, data, { timeout: 300000 }) as any
export const createTopicSynthesis = (topicId: string, data: {
  provider_id: string
  model_name: string
}): Promise<TopicSynthesis> => request.post(`/research_topics/${topicId}/syntheses`, data, { timeout: 180000 }) as any
export const listTopicSyntheses = (topicId: string): Promise<TopicSynthesis[]> => request.get(`/research_topics/${topicId}/syntheses`) as any
export const askTopic = (topicId: string, data: {
  question: string
  history: Array<{ role: 'user' | 'assistant'; content: string }>
  provider_id: string
  model_name: string
  mode: 'question' | 'summary'
}): Promise<TopicAnswer> => request.post(`/research_topics/${topicId}/ask`, data, { timeout: 120000 }) as any

export const getFastWriteStatus = (): Promise<{ enabled: boolean; available: boolean; origin: string; message?: string }> =>
  request.get('/integrations/fastwrite/status', { silent: true }) as any
export const getFastWriteProjects = (): Promise<Array<{ id?: string; projectId?: string; name?: string }>> =>
  request.get('/integrations/fastwrite/projects', { silent: true }) as any
export const createHandoff = (data: {
  project_id: string
  task_id?: string
  topic_id?: string
  include_user_notes: boolean
}): Promise<FastWriteHandoff> => request.post('/integrations/fastwrite/handoffs', data, { timeout: 180000 }) as any
export const listHandoffs = (): Promise<FastWriteHandoff[]> => request.get('/integrations/fastwrite/handoffs') as any
export const retryHandoff = (handoffId: string): Promise<FastWriteHandoff> =>
  request.post(`/integrations/fastwrite/handoffs/${handoffId}/retry`, {}, { timeout: 180000 }) as any

export const handoffDownloadUrl = (handoffId: string, format: 'zip' | 'markdown' | 'bibtex' | 'json' = 'zip') => {
  const apiBase = String(import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
  return `${apiBase}/integrations/fastwrite/handoffs/${encodeURIComponent(handoffId)}/download?format=${format}`
}
