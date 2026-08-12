import type { PaperImportCreated, TaskSnapshot } from './types'
import { settings } from './storage'
import { BACKEND_CANDIDATES, DEFAULT_BACKEND_URL } from './constants'

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

/** 将当前页面的论文 URL 发送给 FastRead 导入。 */
export async function importPaperFromUrl(url: string): Promise<PaperImportCreated> {
  return request<PaperImportCreated>('/api/papers/from_url', {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
}

export async function getTaskStatus(taskId: string): Promise<TaskSnapshot> {
  return request<TaskSnapshot>(`/api/task_status/${encodeURIComponent(taskId)}`)
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
