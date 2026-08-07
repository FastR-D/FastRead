import type { Settings } from './types'

export const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8483'
export const BACKEND_CANDIDATES = [
  'http://127.0.0.1:8483',
  'http://127.0.0.1:3015',
]

export const DEFAULT_SETTINGS: Settings = {
  backendUrl: DEFAULT_BACKEND_URL,
  providerId: '',
  modelName: '',
  quality: 'medium',
  style: 'default',
  formats: ['text'],
  extras: '',
  video_understanding: false,
  video_interval: 5,
  grid_size: [2, 2],
}

export const SETTINGS_KEY = 'fastread-verification-settings'
export const LEGACY_SETTINGS_KEY = 'fastread-cookie-sync-settings'
export const BILINOTE_SETTINGS_KEY = 'bilinote-cookie-sync-settings'
export const TASKS_KEY = 'fastread-tasks'
export const MAX_TASKS = 50
