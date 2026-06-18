export type Platform = 'douyin' | 'bilibili' | 'kuaishou'

export type NoteFormat = 'text' | 'screenshot' | 'link' | 'mindmap' | 'card'
export type TaskStatus =
  | 'PENDING'
  | 'PARSING'
  | 'DOWNLOADING'
  | 'TRANSCRIBING'
  | 'SUMMARIZING'
  | 'FORMATTING'
  | 'SAVING'
  | 'SUCCESS'
  | 'FAILED'

export const NOTE_FORMATS: Array<{ value: NoteFormat, label: string }> = [
  { value: 'text', label: '文字笔记' },
  { value: 'screenshot', label: '关键截图' },
  { value: 'link', label: '来源链接' },
  { value: 'mindmap', label: '思维导图' },
  { value: 'card', label: '知识卡片' },
]

export const NOTE_STYLES: Array<{ value: string, label: string }> = [
  { value: 'default', label: '默认' },
  { value: 'concise', label: '简洁' },
  { value: 'detailed', label: '详细' },
  { value: 'tutorial', label: '教程' },
]

export interface Settings {
  backendUrl: string
  providerId: string
  modelName: string
  quality: 'fast' | 'medium' | 'slow'
  style: string
  formats: NoteFormat[]
  extras: string
  video_understanding: boolean
  video_interval: number
  grid_size: [number, number]
}

export interface DownloaderCookieStatus {
  platform: string
  configured: boolean
  cookie_count: number
  length: number
  updated_at?: string | null
  valid_looking: boolean
  missing_keys: string[]
  warning_keys?: string[]
  warning_message?: string
}

export interface Provider {
  id: string
  name: string
  type: 'built-in' | 'custom' | string
  enabled: number
  logo?: string | null
  api_key?: string
  base_url?: string
}

export interface ProviderUpdatePayload {
  id: string
  name?: string
  api_key?: string
  base_url?: string
  logo?: string
  type?: string
  enabled?: number
}

export interface Model {
  id: number | string
  provider_id?: string
  model_name: string
  enabled?: number
}

export interface TaskResult {
  markdown?: string
  audio_meta?: Record<string, unknown>
  audioMeta?: Record<string, unknown>
  [key: string]: unknown
}

export interface TaskRecord {
  taskId: string
  videoUrl: string
  platform: Platform
  status: TaskStatus
  message?: string
  result?: TaskResult
  createdAt: number
  updatedAt: number
}

export interface TaskSnapshot {
  id?: string
  task_id?: string
  status: TaskStatus
  message?: string
  error?: string | null
  result?: TaskResult | null
  updatedAt?: string | number
  updated_at?: string | number
}

export type TranscriberType = 'fast-whisper' | 'bcut' | 'groq' | 'mlx-whisper'
export type WhisperModelSize = 'tiny' | 'base' | 'small' | 'medium' | 'large-v3' | 'large-v3-turbo'

export interface TranscriberConfig {
  transcriber_type: TranscriberType
  whisper_model_size?: WhisperModelSize
  available_types: Array<{ value: TranscriberType, label: string }>
  whisper_model_sizes: WhisperModelSize[]
  mlx_whisper_available: boolean
}

export interface WhisperModelStatus {
  model_size: WhisperModelSize
  downloaded: boolean
  downloading: boolean
  available?: boolean
}

export interface TranscriberModelsStatus {
  whisper: WhisperModelStatus[]
  mlx_whisper: WhisperModelStatus[]
  mlx_available: boolean
}

export interface DeployStatus {
  backend: {
    status: string
    port: number
  }
  ffmpeg: {
    available: boolean
  }
  cuda: {
    available: boolean
    version?: string | null
    gpu_name?: string | null
  }
  whisper: {
    transcriber_type: TranscriberType | string
    model_size?: string | null
  }
}
