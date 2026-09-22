export type Row = Record<string, any>
let csrf = ''
export function setCsrf(value: string) {
  csrf = value
}

export async function api(path: string, method = 'GET', body?: unknown, key?: string) {
  const headers: Record<string, string> = {}
  if (csrf) headers['X-CSRF-Token'] = csrf
  if (key) headers['Idempotency-Key'] = key
  if (body && !(body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const response = await fetch(`/api${path}`, {
    method,
    headers,
    credentials: 'same-origin',
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  })
  const value = await response.json().catch(() => null)
  if (!response.ok)
    throw new Error(
      typeof value?.detail === 'string'
        ? value.detail
        : response.status === 401
          ? '登录已过期，请重新进入资料库。'
          : `请求未完成（${response.status}），请稍后重试。`
    )
  if (!value) throw new Error('服务返回了无法读取的内容，请稍后重试。')
  return value
}
