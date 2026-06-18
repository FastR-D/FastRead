import { useWebExtensionStorage } from '~/composables/useWebExtensionStorage'
import browser from 'webextension-polyfill'
import type { Settings, TaskRecord } from './types'
import { DEFAULT_BACKEND_URL, DEFAULT_SETTINGS, LEGACY_SETTINGS_KEY, MAX_TASKS, SETTINGS_KEY, TASKS_KEY } from './constants'

export { DEFAULT_BACKEND_URL, DEFAULT_SETTINGS }

void browser.storage.local.get([SETTINGS_KEY, LEGACY_SETTINGS_KEY]).then((stored) => {
  if (!stored[SETTINGS_KEY] && stored[LEGACY_SETTINGS_KEY])
    return browser.storage.local.set({ [SETTINGS_KEY]: stored[LEGACY_SETTINGS_KEY] })
})

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
