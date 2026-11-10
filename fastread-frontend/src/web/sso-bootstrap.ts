import { APP_BASE, API_BASE } from './urls'

type FastNewsIntake = { title: string; authors: string; abstract: string; url: string; venue: string; year: string; external_id: string }
type FastNewsReceipt = { id: string; title: string; awaiting_file: boolean; created: boolean }
type PendingFastNews = { status: 'pending' | 'login-required'; body: FastNewsIntake }
export type FastNewsHandoff =
  | PendingFastNews
  | { status: 'failed'; body: FastNewsIntake; error: string }
  | { status: 'received'; body: FastNewsIntake; receipt: FastNewsReceipt }
  | { status: 'invalid'; error: string }

const pendingKey = `fastread:fastnews:${APP_BASE}`
const intakeFields = ['title', 'authors', 'abstract', 'url', 'venue', 'year', 'external_id'] as const

function intakeBody(value: unknown): FastNewsIntake {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('FastNews 论文信息格式无效，请从原入口重新发送。')
  const record = value as Record<string, unknown>
  const body = Object.fromEntries(intakeFields.map(key => [key, String(record[key] ?? '')])) as FastNewsIntake
  if (!body.title.trim()) throw new Error('FastNews 论文缺少标题，请从原入口重新发送。')
  return body
}

function readPending(): PendingFastNews | null {
  let raw: string | null = null
  try { raw = sessionStorage.getItem(pendingKey) } catch { return null }
  if (!raw) return null
  const stored = JSON.parse(raw)
  if (stored?.status !== 'pending' && stored?.status !== 'login-required') throw new Error('FastNews 待收入信息无效，请从原入口重新发送。')
  return { status: stored.status, body: intakeBody(stored.body) }
}

function savePending(pending: PendingFastNews) {
  try { sessionStorage.setItem(pendingKey, JSON.stringify(pending)) } catch { /* Keep the carrier in the URL for reload/login. */ }
}

export function resumeFastNewsAfterLogin() {
  // Only a successful local login may release a failed-ticket handoff to the new session.
  try {
    const pending = readPending()
    if (pending?.status === 'login-required') savePending({ status: 'pending', body: pending.body })
  } catch { /* An invalid pending record must not prevent signing in. */ }
}

function pendingHandoff(): FastNewsHandoff | null {
  try {
    const params = new URLSearchParams(location.search)
    const previous = readPending()
    let body: FastNewsIntake
    if (location.hash.startsWith('#fastnews=')) {
      // News' fragment is percent-encoded JSON, not a URLSearchParams value. Decode exactly once.
      const carrier = JSON.parse(decodeURIComponent(location.hash.slice('#fastnews='.length)))
      if (!carrier || carrier.source !== 'fastnews') throw new Error('FastNews 来源信息无效，请从原入口重新发送。')
      body = intakeBody({ ...carrier, external_id: carrier.id })
    } else if (params.get('source') === 'fastnews') {
      // Existing documented query entry: fields already use canonical external_id.
      body = intakeBody(Object.fromEntries(params))
    } else {
      return previous
    }
    // Persist paper metadata and its login requirement, never a ticket. Keep the URL until receipt.
    const pending: PendingFastNews = { status: previous?.status ?? 'pending', body }
    savePending(pending)
    return pending
  } catch (error) {
    return { status: 'invalid', error: error instanceof URIError || error instanceof SyntaxError ? 'FastNews 论文信息无法解码，请从原入口重新发送。' : (error as Error).message }
  }
}

function dropSso() {
  const url = new URL(location.href)
  url.searchParams.delete('sso')
  history.replaceState(null, '', url.pathname + url.search + url.hash)
}

async function readJson(path: string, options?: RequestInit) {
  const response = await fetch(`${API_BASE}${path}`, { credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(10000), ...options })
  const payload = await response.json().catch(() => ({}))
  return { response, payload }
}

export async function submitFastNews(body: FastNewsIntake, csrf: string): Promise<FastNewsReceipt> {
  const { response, payload } = await readJson('/integrations/fastnews/intake', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error(typeof payload?.detail === 'string' ? payload.detail : `论文信息尚未收入（HTTP ${response.status}），请重试。`)
  if (!payload || typeof payload.id !== 'string' || !payload.id || typeof payload.title !== 'string' || typeof payload.awaiting_file !== 'boolean' || typeof payload.created !== 'boolean') {
    throw new Error('FastRead 未返回有效收入回执，请重试。')
  }
  try { sessionStorage.removeItem(pendingKey) } catch { /* The server receipt still confirms persistence. */ }
  const url = new URL(location.href)
  if (url.hash.startsWith('#fastnews=')) url.hash = ''
  if (url.searchParams.get('source') === 'fastnews') {
    url.searchParams.delete('source')
    for (const key of intakeFields) url.searchParams.delete(key)
  }
  // Existing PDF attachment deep-link consumes pending=paper_id, not a success flag.
  url.searchParams.set('pending', payload.id)
  history.replaceState(null, '', url.pathname + url.search + url.hash)
  return payload
}

export async function start(loadApp: (user: Record<string, any> | null, handoff: FastNewsHandoff | null) => Promise<void>) {
  let handoff = pendingHandoff()
  const ticket = (new URLSearchParams(location.search).get('sso') || '').trim()
  if (ticket) {
    dropSso()
    try {
      const { response } = await readJson('/auth/research', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ticket }),
      })
      if (!response.ok) throw new Error('登录票据无效或已过期，请登录后继续收入论文。')
      if (handoff?.status === 'login-required') {
        handoff = { status: 'pending', body: handoff.body }
        savePending(handoff)
      }
    } catch {
      if (handoff && 'body' in handoff) {
        handoff = { status: 'login-required', body: handoff.body }
        savePending(handoff)
      }
      // An explicit ticket must not silently fall back to an unrelated existing account.
      await loadApp(null, handoff)
      return
    }
  }
  if (handoff?.status === 'login-required') {
    await loadApp(null, handoff)
    return
  }
  const { response, payload: user } = await readJson('/auth/me')
  if (response.status === 401) {
    await loadApp(null, handoff)
    return
  }
  if (!response.ok) throw new Error('Login verification failed')
  if (handoff?.status === 'pending') {
    const body = handoff.body
    try { handoff = { status: 'received', body, receipt: await submitFastNews(body, String(user.csrf || '')) } }
    catch (error) { handoff = { status: 'failed', body, error: (error as Error).message } }
  }
  await loadApp(user, handoff)
}
