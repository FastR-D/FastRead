import type { Settings } from './types'

export const DEFAULT_BACKEND_URL = 'http://127.0.0.1:3015'
export const BACKEND_CANDIDATES = [
  'http://127.0.0.1:3015',
  'http://localhost:3015',
  'http://127.0.0.1:8483',
  'http://localhost:8483',
  'http://127.0.0.1:8493',
  'http://localhost:8493',
]

export const DEFAULT_SETTINGS: Settings = {
  backendUrl: DEFAULT_BACKEND_URL,
}

export const SETTINGS_KEY = 'reel-mind-cookie-sync-settings'
export const LEGACY_SETTINGS_KEY = 'bilinote-cookie-sync-settings'
