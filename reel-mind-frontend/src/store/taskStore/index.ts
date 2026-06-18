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
  | 'FORMATTING'
  | 'SAVING'
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

export interface InsightScore {
  score: number
  level: string
  reason: string
}

export interface KnowledgeCard {
  type: string
  title: string
  content: string
  evidence?: string
  priority?: number
}

export interface VerificationClaim {
  claim: string
  type: string
  type_label: string
  risk_level: 'low' | 'medium' | 'high'
  risk_topics: string[]
  verdict: string
  confidence: number
  reason: string
  evidence_hint: string
  online?: {
    checked: boolean
    query: string
    verdict: string
    reason: string
    confidence: number
    metrics: {
      coverage: number
      trusted_count: number
      top_overlap: number
    }
    sources: Array<{
      title: string
      url: string
      domain: string
      snippet: string
      trusted: boolean
    }>
  }
  priority?: number
}

export interface ClaimVerification {
  version: number
  external_check: boolean
  overall: {
    status: string
    score: number
    summary: string
    note: string
  }
  claim_counts: {
    total: number
    needs_review: number
    high_risk: number
    medium_risk: number
    online_checked?: number
    online_supported?: number
  }
  online_error?: string
  claims: VerificationClaim[]
}

export interface NoteInsights {
  version: number
  summary?: {
    title?: string
    transcript_type?: string
    transcript_chars?: number
    markdown_chars?: number
  }
  scores: {
    information_density: InsightScore
    credibility: InsightScore
    actionability: InsightScore
  }
  verification?: ClaimVerification
  cards: KnowledgeCard[]
}

export interface TaskFailure {
  category: 'cookie' | 'douyin_detail' | 'provider' | 'asr' | 'llm' | 'media' | 'unknown'
  title: string
  message: string
  retry_hint: string
  raw_message?: string
}

export interface Task {
  id: string
  markdown: string | Markdown[]
  transcript: Transcript
  status: TaskStatus
  platform: string
  collection: CollectionMeta
  audioMeta: AudioMeta
  insights?: NoteInsights
  message?: string
  error?: TaskFailure
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
  removeTask: (id: string) => Promise<void>
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

const EMPTY_AUDIO_META: AudioMeta = {
  cover_url: '',
  duration: 0,
  file_path: '',
  platform: '',
  raw_info: null,
  title: '',
  video_id: '',
}

const isEmptyTranscript = (transcript?: Transcript) =>
  !transcript ||
  (!transcript.full_text &&
    !transcript.language &&
    !transcript.raw &&
    (!transcript.segments || transcript.segments.length === 0))

const isEmptyAudioMeta = (audioMeta?: AudioMeta) =>
  !audioMeta ||
  (!audioMeta.cover_url &&
    !audioMeta.duration &&
    !audioMeta.file_path &&
    !audioMeta.platform &&
    !audioMeta.raw_info &&
    !audioMeta.title &&
    !audioMeta.video_id)

const hasSuccessSnapshotContent = (data: Partial<Omit<Task, 'id' | 'createdAt'>>) =>
  Boolean(
    data.markdown ||
      !isEmptyTranscript(data.transcript) ||
      !isEmptyAudioMeta(data.audioMeta) ||
      data.insights
  )

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
              insights: undefined,
              message: undefined,
              error: undefined,
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
              transcript: task.transcript || emptyTranscript(),
              createdAt: task.createdAt || new Date().toISOString(),
              audioMeta: {
                ...EMPTY_AUDIO_META,
                ...(task.audioMeta || {}),
                platform: task.audioMeta?.platform || 'douyin',
                title: task.audioMeta?.title || '未命名知识卡片',
              },
              insights: task.insights,
              message: task.message || '',
              error: task.error,
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

            if (
              task.status === 'SUCCESS' &&
              data.status === 'SUCCESS' &&
              !hasSuccessSnapshotContent(data)
            ) {
              return task
            }

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
                  message: undefined,
                  error: undefined,
                }
              : t
          ),
        }))
      },

      removeTask: async id => {
        const previousTasks = get().tasks
        const task = previousTasks.find(t => t.id === id)
        const previousCurrentTaskId = get().currentTaskId

        set(state => ({
          tasks: state.tasks.filter(task => task.id !== id),
          currentTaskId: state.currentTaskId === id ? null : state.currentTaskId,
        }))

        if (task) {
          try {
            await delete_task({
              task_id: task.id,
              video_id: task.audioMeta.video_id,
              platform: task.platform,
            })
          } catch (error) {
            set({
              tasks: previousTasks,
              currentTaskId: previousCurrentTaskId,
            })
            throw error
          }
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
