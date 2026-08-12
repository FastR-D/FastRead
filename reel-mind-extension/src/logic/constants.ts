import type { Settings } from './types'

export const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8483'
export const BACKEND_CANDIDATES = [
  'http://127.0.0.1:8483',
  'http://127.0.0.1:3015',
]

export const DEFAULT_SETTINGS: Settings = {
  backendUrl: DEFAULT_BACKEND_URL,
}

export const SETTINGS_KEY = 'fastread-settings'
export const TASKS_KEY = 'fastread-paper-tasks'
export const MAX_TASKS = 50
