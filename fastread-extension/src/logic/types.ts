export interface Settings {
  backendUrl: string
}

export type PaperTaskStatus =
  | 'PENDING'
  | 'PARSING'
  | 'RUNNING'
  | 'SUCCESS'
  | 'FAILED'

export interface PaperImportCreated {
  task_id: string
  status: PaperTaskStatus | string
}

export interface TaskRecord {
  taskId: string
  input: string
  inputMode: 'url'
  platform: 'paper'
  status: PaperTaskStatus | string
  message?: string
  createdAt: number
  updatedAt: number
}

export interface TaskSnapshot {
  id?: string
  task_id?: string
  status: PaperTaskStatus | string
  message?: string
  error?: string | null
  updatedAt?: string | number
  updated_at?: string | number
}
