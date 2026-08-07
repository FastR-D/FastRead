import type {
  DeployStatus,
  DownloaderCookieStatus,
  Model,
  Provider,
  ProviderUpdatePayload,
  TaskSnapshot,
  TranscriberConfig,
  TranscriberModelsStatus,
  TranscriberType,
  VerificationTaskCreated,
  WhisperModelSize,
} from './types'
import { settings } from './storage'
import { BACKEND_CANDIDATES, DEFAULT_BACKEND_URL } from './constants'

export interface ChatMessage {
  role: 'user' | 'assistant' | string
  content: string
}

interface ApiEnvelope<T> {
  code: number
  msg: string
  data: T
}

function normalizeBackendUrl(url: string): string {
  return url.trim().replace(/\/$/, '')
}

function configuredBackendUrl(): string {
  return normalizeBackendUrl(settings.value?.backendUrl || DEFAULT_BACKEND_URL)
}

export function getConfiguredBackendUrl(): string {
  return configuredBackendUrl()
}

function backendCandidates(): string[] {
  return Array.from(new Set([
    configuredBackendUrl(),
    ...BACKEND_CANDIDATES,
  ].map(normalizeBackendUrl).filter(Boolean)))
}

async function fetchJson<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${baseUrl}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok)
    throw new Error(`HTTP ${res.status}: ${await res.text()}`)

  const body = (await res.json()) as ApiEnvelope<T>
  if (body.code !== 0)
    throw new Error(body.msg || '后端返回失败')
  return body.data
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const errors: string[] = []
  for (const baseUrl of backendCandidates()) {
    try {
      const data = await fetchJson<T>(baseUrl, path, init)
      if (settings.value.backendUrl !== baseUrl)
        settings.value.backendUrl = baseUrl
      return data
    }
    catch (e) {
      errors.push(`${baseUrl}: ${(e as Error).message}`)
    }
  }
  throw new Error(`无法连接 FastRead 后端。已尝试：${errors.join('；')}`)
}

export async function setDownloaderCookie(platform: string, cookie: string): Promise<void> {
  await request('/api/update_downloader_cookie', {
    method: 'POST',
    body: JSON.stringify({ platform, cookie }),
  })
}

export async function getDownloaderCookie(platform: string): Promise<string | null> {
  const payload = await request<{ platform: string, cookie?: string } | null>(`/api/get_downloader_cookie/${platform}`)
  return payload?.cookie || null
}

export async function getDownloaderCookieStatus(platform: string): Promise<DownloaderCookieStatus> {
  return request<DownloaderCookieStatus>(`/api/downloader_cookie_status/${platform}`)
}

export async function createVerificationTask(payload: {
  text?: string
  url?: string
  max_claims?: number
  verification_depth?: string
  source_policy?: string
  model_name?: string
  provider_id?: string
}): Promise<VerificationTaskCreated> {
  return request<VerificationTaskCreated>('/api/verification_tasks', {
    method: 'POST',
    body: JSON.stringify({
      goal: 'verify',
      verification_depth: 'deep',
      source_policy: 'authoritative',
      max_claims: 50,
      ...payload,
    }),
  })
}

export async function getProviders(): Promise<Provider[]> {
  return request<Provider[]>('/api/get_all_providers')
}

export async function getProviderById(id: string): Promise<Provider> {
  return request<Provider>(`/api/get_provider_by_id/${encodeURIComponent(id)}`)
}

export async function addProvider(payload: Omit<ProviderUpdatePayload, 'id'> & { type: string }): Promise<string | number> {
  return request<string | number>('/api/add_provider', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateProvider(payload: ProviderUpdatePayload): Promise<Provider> {
  return request<Provider>('/api/update_provider', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function connectTest(id: string): Promise<void> {
  await request<unknown>('/api/connect_test', {
    method: 'POST',
    body: JSON.stringify({ id }),
  })
}

export async function listAllModels(providerId?: string): Promise<Model[]> {
  return providerId
    ? request<Model[]>(`/api/model_list/${encodeURIComponent(providerId)}`)
    : request<Model[]>('/api/model_list')
}

export async function getModelsByProvider(providerId: string): Promise<Model[]> {
  return request<Model[]>(`/api/model_enable/${encodeURIComponent(providerId)}`)
}

export async function addModel(providerId: string, modelName: string): Promise<void> {
  await request<unknown>('/api/models', {
    method: 'POST',
    body: JSON.stringify({ provider_id: providerId, model_name: modelName }),
  })
}

export async function deleteModel(modelId: number | string): Promise<void> {
  await request<unknown>(`/api/models/delete/${encodeURIComponent(String(modelId))}`)
}

export async function getTranscriberConfig(): Promise<TranscriberConfig> {
  return request<TranscriberConfig>('/api/transcriber_config')
}

export async function setTranscriberConfig(
  transcriberType: TranscriberType,
  whisperModelSize?: WhisperModelSize,
): Promise<TranscriberConfig> {
  return request<TranscriberConfig>('/api/transcriber_config', {
    method: 'POST',
    body: JSON.stringify({
      transcriber_type: transcriberType,
      whisper_model_size: whisperModelSize,
    }),
  })
}

export async function getTranscriberModelsStatus(): Promise<TranscriberModelsStatus> {
  return request<TranscriberModelsStatus>('/api/transcriber_models_status')
}

export async function downloadTranscriberModel(
  modelSize: WhisperModelSize,
  transcriberType: TranscriberType = 'fast-whisper',
): Promise<void> {
  await request<unknown>('/api/transcriber_download', {
    method: 'POST',
    body: JSON.stringify({
      model_size: modelSize,
      transcriber_type: transcriberType,
    }),
  })
}

export async function getDeployStatus(): Promise<DeployStatus> {
  return request<DeployStatus>('/api/deploy_status')
}

export async function getSysHealth(): Promise<{ ok: boolean, msg?: string }> {
  try {
    await request<unknown>('/api/sys_health')
    return { ok: true }
  }
  catch (e) {
    return { ok: false, msg: (e as Error).message }
  }
}

export async function getTaskStatus(taskId: string): Promise<TaskSnapshot> {
  return request<TaskSnapshot>(`/api/task_status/${encodeURIComponent(taskId)}`)
}

export async function indexChatTask(taskId: string): Promise<{ status?: string, indexed?: boolean }> {
  return request<{ status?: string, indexed?: boolean }>('/api/chat/index', {
    method: 'POST',
    body: JSON.stringify({ task_id: taskId }),
  })
}

export async function getChatStatus(taskId: string): Promise<{ status: 'idle' | 'indexing' | 'indexed' | 'failed' | 'disabled', indexed: boolean }> {
  return request<{ status: 'idle' | 'indexing' | 'indexed' | 'failed' | 'disabled', indexed: boolean }>(
    `/api/chat/status?task_id=${encodeURIComponent(taskId)}`,
  )
}

export async function askChat(payload: {
  task_id?: string
  scope?: 'task' | 'library'
  question: string
  history: ChatMessage[]
  provider_id: string
  model_name: string
}): Promise<unknown> {
  return request<unknown>('/api/chat/ask', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function resolveImageUrl(url?: string | null): string {
  if (!url)
    return ''
  if (/^https?:\/\//i.test(url) || /^data:/i.test(url))
    return url
  const path = url.startsWith('/') ? url : `/${url}`
  return `${configuredBackendUrl()}${path}`
}

export function absolutizeMarkdownImages(markdown: string): string {
  return markdown.replace(/!\[([^\]]*)\]\((?!https?:\/\/|data:)([^)]+)\)/g, (_match, alt: string, url: string) => {
    return `![${alt}](${resolveImageUrl(url.trim())})`
  })
}

export function stripSourceLink(markdown: string): string {
  return markdown
    .replace(/^\s*来源链接[:：].*$/gm, '')
    .replace(/\n{3,}/g, '\n\n')
}

export async function ping(): Promise<boolean> {
  try {
    await request('/api/sys_check')
    return true
  }
  catch {
    return false
  }
}
