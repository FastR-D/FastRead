import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'

const MAX_ATTEMPTS = 4
const RETRY_INTERVAL = 2000

const healthClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 3000,
})

export type BackendStartupStatus = 'checking' | 'ready' | 'failed'

function describeError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.code === 'ECONNABORTED') return '健康检查超时，后端进程可能没有响应。'
    if (error.response) return `健康检查返回 HTTP ${error.response.status}。`
    return '无法连接后端健康检查接口。'
  }
  return error instanceof Error ? error.message : '后端健康检查失败。'
}

export const useCheckBackend = () => {
  const [status, setStatus] = useState<BackendStartupStatus>('checking')
  const [attempt, setAttempt] = useState(0)
  const [error, setError] = useState('')
  const [checkCycle, setCheckCycle] = useState(0)

  const retry = useCallback(() => setCheckCycle(cycle => cycle + 1), [])

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const wait = () => new Promise<void>(resolve => {
      timer = setTimeout(resolve, RETRY_INTERVAL)
    })

    const check = async () => {
      setStatus('checking')
      setAttempt(0)
      setError('')

      for (let nextAttempt = 1; nextAttempt <= MAX_ATTEMPTS && !cancelled; nextAttempt += 1) {
        setAttempt(nextAttempt)
        try {
          await healthClient.get('/sys_health')
          if (cancelled) return
          setStatus('ready')
          setError('')
          return
        }
        catch (nextError) {
          if (cancelled) return
          setError(describeError(nextError))
          if (nextAttempt < MAX_ATTEMPTS) await wait()
        }
      }

      if (!cancelled) setStatus('failed')
    }

    check()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [checkCycle])

  return {
    status,
    attempt,
    error,
    initialized: status === 'ready',
    retry,
  }
}
