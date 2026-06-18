import type { Settings } from './types'

export const DEFAULT_BACKEND_URL = 'http://127.0.0.1:3015'
export const BACKEND_CANDIDATES = [
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

export const SETTINGS_KEY = 'reel-mind-cookie-sync-settings'
export const LEGACY_SETTINGS_KEY = 'bilinote-cookie-sync-settings'
export const TASKS_KEY = 'reel-mind-tasks'
export const MAX_TASKS = 50
