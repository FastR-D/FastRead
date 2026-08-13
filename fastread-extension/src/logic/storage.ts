import type { Settings, TaskRecord } from './types'
import { DEFAULT_BACKEND_URL, DEFAULT_SETTINGS, MAX_TASKS, SETTINGS_KEY, TASKS_KEY } from './constants'
import { useWebExtensionStorage } from '~/composables/useWebExtensionStorage'

export { DEFAULT_BACKEND_URL, DEFAULT_SETTINGS }

export const { data: settings, dataReady: settingsReady } = useWebExtensionStorage<Settings>(
  SETTINGS_KEY,
  DEFAULT_SETTINGS,
  {
    mergeDefaults: stored => ({
      ...DEFAULT_SETTINGS,
      ...(stored as Partial<Settings>),
    }),
  },
)

export const { data: tasks, dataReady: tasksReady } = useWebExtensionStorage<TaskRecord[]>(
  TASKS_KEY,
  [],
  {
    mergeDefaults: stored => Array.isArray(stored) ? stored : [],
  },
)

export function upsertTask(record: TaskRecord) {
  const idx = tasks.value.findIndex(t => t.taskId === record.taskId)
  if (idx >= 0)
    tasks.value.splice(idx, 1, { ...tasks.value[idx], ...record })
  else
    tasks.value.unshift(record)
  tasks.value = tasks.value.slice(0, MAX_TASKS)
}
