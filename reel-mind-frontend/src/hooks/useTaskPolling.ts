import { useEffect, useRef } from 'react'
import { useTaskStore } from '@/store/taskStore'
import { get_task_status } from '@/services/note.ts'
import toast from 'react-hot-toast'

const INITIAL_RETRY_DELAY = 3000
const MAX_RETRY_DELAY = 30000

type PollRetryState = {
  attempts: number
  nextRetryAt: number
}

const getRetryDelay = (attempts: number) => {
  const exponentialDelay = INITIAL_RETRY_DELAY * 2 ** Math.max(0, attempts - 1)
  const cappedDelay = Math.min(exponentialDelay, MAX_RETRY_DELAY)
  const jitter = Math.round(cappedDelay * 0.2 * Math.random())
  return cappedDelay + jitter
}

export const useTaskPolling = (interval = 3000) => {
  const tasks = useTaskStore(state => state.tasks)
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)

  const tasksRef = useRef(tasks)
  const retryStateRef = useRef<Map<string, PollRetryState>>(new Map())
  const pollingRef = useRef(false)

  // 每次 tasks 更新，把最新的 tasks 同步进去
  useEffect(() => {
    tasksRef.current = tasks
    const liveTaskIds = new Set(tasks.map(task => task.id))
    for (const taskId of retryStateRef.current.keys()) {
      if (!liveTaskIds.has(taskId)) {
        retryStateRef.current.delete(taskId)
      }
    }
  }, [tasks])

  useEffect(() => {
    const retryStates = retryStateRef.current

    const timer = setInterval(async () => {
      if (pollingRef.current) return

      const pendingTasks = tasksRef.current.filter(
        task => task.status != 'SUCCESS' && task.status != 'FAILED'
      )

      // 无活跃任务时跳过轮询
      if (pendingTasks.length === 0) return

      pollingRef.current = true

      try {
        const now = Date.now()

        for (const task of pendingTasks) {
          const retryState = retryStateRef.current.get(task.id)
          if (retryState && retryState.nextRetryAt > now) {
            continue
          }

          try {
            const res = await get_task_status(task.id)
            const { status } = res

            retryStateRef.current.delete(task.id)

            const hasSuccessContent = Boolean(
              res.result?.markdown || res.result?.transcript || res.result?.audioMeta || res.result?.insights
            )

            if (status && (status !== task.status || (status === 'SUCCESS' && hasSuccessContent))) {
              if (status === 'SUCCESS') {
                const { markdown, transcript, audioMeta, insights } = res.result || {}
                if (task.status !== 'SUCCESS') {
                  toast.success('笔记生成成功')
                }
                updateTaskContent(task.id, {
                  status,
                  markdown,
                  transcript,
                  audioMeta,
                  insights,
                  message: undefined,
                  error: undefined,
                })
              } else if (status === 'FAILED') {
                updateTaskContent(task.id, {
                  status,
                  message: res.message,
                  error: res.error,
                })
                console.warn(`⚠️ 任务 ${task.id} 失败`, res.error || res.message)
              } else {
                updateTaskContent(task.id, { status })
              }
            }
          } catch (e) {
            const attempts = (retryState?.attempts || 0) + 1
            const retryDelay = getRetryDelay(attempts)
            retryStateRef.current.set(task.id, {
              attempts,
              nextRetryAt: Date.now() + retryDelay,
            })

            if (attempts === 1 || attempts % 3 === 0) {
              console.warn(
                `任务 ${task.id} 轮询请求失败，将在 ${Math.round(retryDelay / 1000)} 秒后重试`,
                e
              )
            } else {
              console.debug(`任务 ${task.id} 轮询请求失败，等待退避重试`, e)
            }
          }
        }
      } finally {
        pollingRef.current = false
      }
    }, interval)

    return () => {
      clearInterval(timer)
      retryStates.clear()
      pollingRef.current = false
    }
  }, [interval, updateTaskContent])
}
