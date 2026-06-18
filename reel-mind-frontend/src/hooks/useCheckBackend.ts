import { useEffect, useState } from 'react'
import axios from 'axios'

const MAX_RETRIES = 3
const RETRY_INTERVAL = 10000 // 10秒

const healthClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 3000,
})

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

export const useCheckBackend = () => {
  const [loading, setLoading] = useState(false)
  const [initialized, setInitialized] = useState(false)

  useEffect(() => {
    let retries = 0
    let cancelled = false

    const check = async () => {
      try {
        await healthClient.get('/sys_check')
        if (cancelled) return
        setInitialized(true)
        setLoading(false)
      } catch {
        if (cancelled) return
        if (retries === 0) {
          // 第一次失败时开始显示加载状态
          setLoading(true)
        }

        if (retries < MAX_RETRIES) {
          retries++
          setTimeout(check, RETRY_INTERVAL)
        } else {
          // 达到重试上限，继续轮询直到后端就绪
          waitUntilBackendReady()
        }
      }
    }

    const waitUntilBackendReady = async () => {
      while (!cancelled) {
        try {
          await healthClient.get('/sys_health')
          if (cancelled) return
          setInitialized(true)
          setLoading(false)
          break
        } catch {
          await sleep(RETRY_INTERVAL)
        }
      }
    }

    check()
    return () => {
      cancelled = true
    }
  }, [])

  return { loading, initialized }
}
