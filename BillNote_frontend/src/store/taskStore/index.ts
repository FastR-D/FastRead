import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { delete_task, generateNote, list_generated_tasks, update_task_collection } from '@/services/note.ts'
import { v4 as uuidv4 } from 'uuid'
import toast from 'react-hot-toast'
import { get, set, del } from 'idb-keyval'

export type TaskStatus =
  | 'PENDING'
  | 'PARSING'
  | 'DOWNLOADING'
  | 'TRANSCRIBING'
  | 'SUMMARIZING'
  | 'RUNNING'
  | 'SUCCESS'
  | 'FAILED'

export interface AudioMeta {
  cover_url: string
  duration: number
  file_path: string
  platform: string
  raw_info: any
  title: string
  video_id: string
}

export interface Segment {
  start: number
  end: number
  text: string
}

export interface Transcript {
  full_text: string
  language: string
  raw: any
  segments: Segment[]
}

export interface Markdown {
  ver_id: string
  content: string
  style: string
  model_name: string
  created_at: string
}

export interface CollectionMeta {
  folder: string
  tags: string[]
  note: string
}

export interface Task {
  id: string
  markdown: string | Markdown[]
  transcript: Transcript
  status: TaskStatus
  platform: string
  collection: CollectionMeta
  audioMeta: AudioMeta
  createdAt: string
  formData: {
    video_url: string
    link: undefined | boolean
    screenshot: undefined | boolean
    platform: string
    quality: string
    model_name: string
    provider_id: string
    style?: string
    extras?: string
    format?: string[]
    video_understanding?: boolean
    video_interval?: number
    grid_size?: number[]
    collection_folder?: string
    collection_tags?: string
    collection_note?: string
  }
}

interface TaskStore {
  tasks: Task[]
  currentTaskId: string | null
  addPendingTask: (taskId: string, platform: string, formData: any) => void
  updateTaskContent: (id: string, data: Partial<Omit<Task, 'id' | 'createdAt'>>) => void
  updateTaskCollection: (id: string, collection: Partial<CollectionMeta>) => void
  loadSavedTasks: () => Promise<void>
  removeTask: (id: string) => void
  clearTasks: () => void
  setCurrentTask: (taskId: string | null) => void
  getCurrentTask: () => Task | null
  retryTask: (id: string, payload?: any) => void
}

const DEFAULT_COLLECTION: CollectionMeta = {
  folder: '默认收藏夹',
  tags: [],
  note: '',
}

const collectionSyncTimers = new Map<string, ReturnType<typeof setTimeout>>()

const parseTags = (value?: string) =>
  (value || '')
    .split(/[，,\s]+/)
    .map(tag => tag.trim())
    .filter(Boolean)

const getCollectionFromForm = (formData: any): CollectionMeta => ({
  folder: formData?.collection_folder?.trim() || DEFAULT_COLLECTION.folder,
  tags: parseTags(formData?.collection_tags),
  note: formData?.collection_note?.trim() || '',
})

const emptyTranscript = (): Transcript => ({
  full_text: '',
  language: '',
  raw: null,
  segments: [],
})

export const useTaskStore = create<TaskStore>()(
  persist(
    (set, get) => ({
      tasks: [],
      currentTaskId: null,

      addPendingTask: (taskId: string, platform: string, formData: any) =>
        set(state => ({
          tasks: [
            {
              formData,
              id: taskId,
              status: 'PENDING',
              markdown: '',
              platform,
              collection: getCollectionFromForm(formData),
              transcript: emptyTranscript(),
              createdAt: new Date().toISOString(),
              audioMeta: {
                cover_url: '',
                duration: 0,
                file_path: '',
                platform: '',
                raw_info: null,
                title: '',
                video_id: '',
              },
            },
            ...state.tasks,
          ],
          currentTaskId: taskId,
        })),

      loadSavedTasks: async () => {
        const savedTasks = await list_generated_tasks()
        if (!Array.isArray(savedTasks)) return

        set(state => {
          const existingIds = new Set(state.tasks.map(task => task.id))
          const restoredTasks: Task[] = savedTasks
            .filter((task: any) => task?.id && !existingIds.has(task.id))
            .map((task: any) => ({
              id: task.id,
              status: task.status || 'SUCCESS',
              markdown: task.markdown || '',
              platform: task.audioMeta?.platform || 'douyin',
              collection: {
                ...DEFAULT_COLLECTION,
                ...(task.collection || {}),
                tags: Array.isArray(task.collection?.tags) ? task.collection.tags : [],
              },
              transcript: emptyTranscript(),
              createdAt: task.createdAt
                ? new Date(Number(task.createdAt) * 1000).toISOString()
                : new Date().toISOString(),
              audioMeta: {
                cover_url: task.audioMeta?.cover_url || '',
                duration: task.audioMeta?.duration || 0,
                file_path: task.audioMeta?.file_path || '',
                platform: task.audioMeta?.platform || 'douyin',
                raw_info: task.audioMeta?.raw_info || null,
                title: task.audioMeta?.title || '未命名知识卡片',
                video_id: task.audioMeta?.video_id || '',
              },
              formData: {
                video_url: task.videoUrl || '',
                link: false,
                screenshot: false,
                platform: 'douyin',
                quality: 'medium',
                model_name: '',
                provider_id: '',
                style: 'minimal',
                format: ['toc', 'summary', 'mindmap'],
              },
            }))

          const currentTask = state.tasks.find(task => task.id === state.currentTaskId)
          const keepActiveTask =
            currentTask && currentTask.status !== 'SUCCESS' && currentTask.status !== 'FAILED'
          if (restoredTasks.length === 0) {
            return keepActiveTask ? state : { ...state, currentTaskId: null }
          }

          return {
            tasks: [...state.tasks, ...restoredTasks].sort(
              (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
            ),
            currentTaskId: keepActiveTask ? state.currentTaskId : null,
          }
        })
      },

      updateTaskContent: (id, data) =>
        set(state => ({
          tasks: state.tasks.map(task => {
            if (task.id !== id) return task

            if (task.status === 'SUCCESS' && data.status === 'SUCCESS') return task

            if (typeof data.markdown === 'string') {
              const prev = task.markdown
              const newVersion: Markdown = {
                ver_id: `${task.id}-${uuidv4()}`,
                content: data.markdown,
                style: task.formData.style || '',
                model_name: task.formData.model_name || '',
                created_at: new Date().toISOString(),
              }

              let updatedMarkdown: Markdown[]
              if (Array.isArray(prev)) {
                updatedMarkdown = [newVersion, ...prev]
              } else {
                updatedMarkdown = [
                  newVersion,
                  ...(typeof prev === 'string' && prev
                    ? [
                        {
                          ver_id: `${task.id}-${uuidv4()}`,
                          content: prev,
                          style: task.formData.style || '',
                          model_name: task.formData.model_name || '',
                          created_at: new Date().toISOString(),
                        },
                      ]
                    : []),
                ]
              }

              return {
                ...task,
                ...data,
                markdown: updatedMarkdown,
              }
            }

            return { ...task, ...data }
          }),
        })),

      updateTaskCollection: (id, collection) => {
        let nextCollection: CollectionMeta | null = null

        set(state => ({
          tasks: state.tasks.map(task => {
            if (task.id !== id) return task

            nextCollection = {
              ...(task.collection || DEFAULT_COLLECTION),
              ...collection,
            }

            return {
              ...task,
              collection: nextCollection,
            }
          }),
        }))

        if (!nextCollection) return

        const existingTimer = collectionSyncTimers.get(id)
        if (existingTimer)
          clearTimeout(existingTimer)

        const timer = setTimeout(() => {
          const latest = get().tasks.find(task => task.id === id)?.collection || nextCollection!
          update_task_collection({
            task_id: id,
            collection_folder: latest.folder,
            collection_tags: latest.tags || [],
            collection_note: latest.note || '',
          }).catch(err => {
            console.warn('同步收藏信息失败:', err)
          }).finally(() => {
            collectionSyncTimers.delete(id)
          })
        }, 500)

        collectionSyncTimers.set(id, timer)
      },

      getCurrentTask: () => {
        const currentTaskId = get().currentTaskId
        return get().tasks.find(task => task.id === currentTaskId) || null
      },

      retryTask: async (id: string, payload?: any) => {
        if (!id) {
          toast.error('任务不存在')
          return
        }
        const task = get().tasks.find(task => task.id === id)
        if (!task) return

        const newFormData = payload || task.formData
        await generateNote({
          ...newFormData,
          task_id: id,
        })

        set(state => ({
          tasks: state.tasks.map(t =>
            t.id === id
              ? {
                  ...t,
                  formData: newFormData,
                  collection: getCollectionFromForm(newFormData),
                  status: 'PENDING',
                }
              : t
          ),
        }))
      },

      removeTask: async id => {
        const task = get().tasks.find(t => t.id === id)

        set(state => ({
          tasks: state.tasks.filter(task => task.id !== id),
          currentTaskId: state.currentTaskId === id ? null : state.currentTaskId,
        }))

        if (task) {
          await delete_task({
            task_id: task.id,
            video_id: task.audioMeta.video_id,
            platform: task.platform,
          })
        }
      },

      clearTasks: () => set({ tasks: [], currentTaskId: null }),

      setCurrentTask: taskId => set({ currentTaskId: taskId }),
    }),
    {
      name: 'task-storage',
      storage: createJSONStorage(() => ({
        getItem: async (name: string): Promise<string | null> => {
          const value = await get(name)
          return value ?? null
        },
        setItem: async (name: string, value: string): Promise<void> => {
          await set(name, value)
        },
        removeItem: async (name: string): Promise<void> => {
          await del(name)
        },
      })),
    }
  )
)
