import request from '@/utils/request'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatSource {
  text: string
  source_type: 'paper_page'
  task_id?: string
  title?: string
  section_title?: string
  page_start?: number
  page_end?: number
  exact_quote?: string
  source_url?: string
  doi?: string
}

export interface AskResponse {
  answer: string
  sources: ChatSource[]
  grounding_status?: 'source_grounded' | 'retrieval_miss' | 'requested_page_missing' | 'response_format_invalid' | 'citation_missing' | 'citation_rejected' | 'insufficient_source' | string
  grounding_detail?: string
  retrieval_strategy?: string
  retrieved_pages?: number[]
}

export type IndexStatus = 'disabled' | 'idle' | 'indexing' | 'indexed' | 'failed'

export interface ChatStatusResponse {
  indexed: boolean
  status: IndexStatus
  detail?: string
}

export const indexTask = async (taskId: string): Promise<ChatStatusResponse> => {
  return await request.post('/chat/index', { task_id: taskId })
}

export const askQuestion = async (data: {
  task_id?: string
  scope?: 'task' | 'library'
  question: string
  history: ChatMessage[]
  provider_id: string
  model_name: string
}): Promise<AskResponse> => {
  return await request.post('/chat/ask', data, { timeout: 60000 })
}

export const getChatStatus = async (taskId: string): Promise<ChatStatusResponse> => {
  return await request.get(`/chat/status?task_id=${taskId}`)
}
