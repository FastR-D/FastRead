export type Platform = 'douyin' | 'bilibili' | 'kuaishou'

export interface Settings {
  backendUrl: string
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
