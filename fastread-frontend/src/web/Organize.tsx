import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'

export type Job = Record<string, any> & { id: string; kind: string; resource_id: string; state: string; created?: number }
type Status = 'idle' | 'pending' | 'succeeded' | 'failed'
const OrganizeContext = createContext<{
  status: (id: string) => Status
  organize: (ids: string[], body: unknown) => Promise<void>
} | null>(null)

export function OrganizeProvider({ jobs, submit, api, children }: {
  jobs: Job[]; submit: (path: string, body?: unknown) => Promise<Job>; api: (path: string) => Promise<Job>; children: ReactNode
}) {
  const locks = useRef(new Set<string>())
  const [local, setLocal] = useState<Record<string, Job | 'pending' | 'failed'>>({})
  // A submitted job can fall outside the recent-jobs page; keep tracking it by ID.
  const missing = Object.values(local).filter((j): j is Job => typeof j !== 'string' && ['queued', 'running'].includes(j.state) && !jobs.some(remote => remote.id === j.id)).map(j => j.id).join(',')
  useEffect(() => {
    if (!missing) return
    let stopped = false
    async function refresh() {
      await Promise.all(missing.split(',').map(async id => {
        try {
          const job = await api(`/jobs/${id}`)
          if (!stopped) setLocal(current => current[job.resource_id] !== 'pending' && typeof current[job.resource_id] === 'object' && (current[job.resource_id] as Job).id === id ? { ...current, [job.resource_id]: job } : current)
        } catch { /* Keep the pending state until the server is reachable again. */ }
      }))
    }
    void refresh()
    const timer = setInterval(refresh, 3000)
    return () => { stopped = true; clearInterval(timer) }
  }, [missing, api])
  function status(id: string): Status {
    const own = local[id]
    if (own === 'pending' || own === 'failed') return own
    const remote = jobs.filter(j => j.kind === 'organize' && j.resource_id === id)
    const job = own ? remote.find(j => j.id === own.id) || own : remote[0]
    if (!job) return 'idle'
    if (['queued', 'running'].includes(job.state)) return 'pending'
    return job.state === 'succeeded' ? 'succeeded' : 'failed'
  }
  async function organize(ids: string[], body: unknown) {
    const ready = ids.filter(id => !locks.current.has(id) && status(id) !== 'pending')
    ready.forEach(id => locks.current.add(id))
    setLocal(current => ({ ...current, ...Object.fromEntries(ready.map(id => [id, 'pending' as const])) }))
    await Promise.all(ready.map(async id => {
      try {
        const job = await submit(`/papers/${id}/organize`, body)
        setLocal(current => ({ ...current, [id]: job }))
      } catch {
        setLocal(current => ({ ...current, [id]: 'failed' }))
      } finally { locks.current.delete(id) }
    }))
  }
  return <OrganizeContext.Provider value={{ status, organize }}>{children}</OrganizeContext.Provider>
}

export function OrganizeButton({ ids, body, disabled, label = 'AI 整理', className = 'quiet' }: {
  ids: string[]; body: unknown; disabled?: boolean; label?: string; className?: string
}) {
  const context = useContext(OrganizeContext)
  if (!context) throw new Error('OrganizeButton requires OrganizeProvider')
  const states = ids.map(context.status)
  const pending = states.includes('pending')
  const failed = !pending && states.includes('failed')
  const done = !!ids.length && states.every(s => s === 'succeeded')
  return <span className="organize-control">
    <button className={className} disabled={disabled || !ids.length || pending} aria-busy={pending}
      onClick={() => void context.organize(ids, body)}>
      {pending ? <><span className="organize-spinner" aria-hidden="true" />正在整理…</> : failed ? '整理失败，点击重试' : label}
    </button>
    <span className="organize-status" role="status" aria-live="polite">
      {pending ? 'AI 正在整理原理与标签，完成后会自动更新。' : failed ? '整理未完成，请稍后重试。' : done ? '整理完成' : ''}
    </span>
  </span>
}
