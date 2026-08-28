import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { del, get, set } from 'idb-keyval'
import toast from 'react-hot-toast'
import {
  delete_collection_folder,
  delete_paper,
  list_generated_tasks,
  update_task_collection,
  type PaperInput,
  type TaskSnapshot,
} from '@/services/note'
import {
  updateWorkspaceResumeState,
  type WorkspaceLocation,
  type WorkspaceResumeState,
} from '@/utils/workspaceNavigation'
import {
  collectionFolderKey,
  DEFAULT_COLLECTION_FOLDER,
  mergeCollectionFolders,
  normalizeCollectionFolder,
  validateCollectionFolder,
} from '@/utils/collections'

export type TaskStatus =
  | 'PENDING'
  | 'PARSING_DOCUMENT'
  | 'GENERATING_REPORT'
  | 'FINDING_RELATED_WORK'
  | 'WRITING_REPORT'
  | 'SUCCESS'
  | 'FAILED'

export interface PaperPage {
  page: number
  text: string
  start?: number
  end?: number
}

export interface AcademicGate {
  level: 'A1' | 'A2' | 'B1' | 'U' | 'N/A'
  label: string
  gate_passed: boolean
  formal_identity_passed?: boolean
  identity_complete: boolean
  identity_fields_complete?: boolean
  is_top4_security: boolean
  is_core_venue?: boolean
  venue_track?: 'security' | 'systems' | 'ai' | ''
  identity_source?: string
  identity_status:
    | 'confirmed_core'
    | 'claimed_core_unverified'
    | 'confirmed_formal_other'
    | 'preprint'
    | 'incomplete'
    | 'retracted_or_withdrawn'
  publication_status: 'formally_published' | 'published' | 'unknown' | 'preprint' | 'withdrawn' | 'retracted'
  integrity_status?: string
  title?: string
  authors?: string[]
  year?: number | null
  doi?: string
  venue?: { id?: string; name?: string; short_name?: string; track?: string; raw?: string }
  official_record?: boolean
  official_record_verified?: boolean
  registry_record_verified?: boolean
  registry_name?: string
  registry_record_url?: string
  warnings?: string[]
}

export interface PaperDocument {
  id: string
  title: string
  authors: string[]
  venue?: { id?: string; name?: string; short_name?: string; track?: string; raw?: string }
  year?: number | null
  doi?: string
  source_url?: string
  resolved_source_url?: string
  pdf_url?: string
  filename?: string
  content_hash?: string
  formal_record_url?: string
  page_count: number
  page_count_total?: number
  page_count_parsed?: number
  text_chars?: number
  text_truncated?: boolean
  pages: PaperPage[]
  academic_gate?: AcademicGate
}

export interface CollectionMeta {
  folder: string
  tags: string[]
  note: string
}

export interface ReadingReportEvidence {
  source_id?: string
  source_url?: string
  page_start?: number | null
  page_end?: number | null
  exact_quote: string
  verified_in_source: boolean
}

export interface ReadingReport {
  version: number
  report_version?: string
  generated_at: string
  title: string
  executive_summary: string
  key_questions: Array<{
    question: string
    answer: string
    why_it_matters: string
    evidence: ReadingReportEvidence[]
  }>
  process: Array<{ step: string; description: string; evidence?: ReadingReportEvidence[] }>
  contributions: Array<{
    title: string
    description: string
    evidence?: string | ReadingReportEvidence[]
  }>
  limitations: string[]
  terms: Array<{ term: string; explanation: string }>
  suggested_questions: string[]
  academic_gate: AcademicGate
  report_grounding_status?: string
  model?: { provider_id: string; model_name: string }
}

export interface NoteInsights {
  version?: number
  reading_report?: ReadingReport
  academic_gate?: AcademicGate
  personal_summary?: {
    content: string
    updated_at: string
    max_chars: number
  }
}

export interface TaskFailure {
  category: 'parsing' | 'fetching' | 'model' | 'storage' | 'unknown'
  title: string
  message: string
  retry_hint?: string
  raw_message?: string
}

export interface Task {
  id: string
  kind: 'paper'
  status: TaskStatus
  title: string
  paperInput: PaperInput
  paperDocument?: PaperDocument
  insights?: NoteInsights
  collection: CollectionMeta
  message?: string
  error?: TaskFailure
  createdAt: string
  updatedAt?: string
  readingProgress?: WorkspaceResumeState
}

interface TaskStore {
  tasks: Task[]
  currentTaskId: string | null
  collectionFolders: string[]
  collectionSync: Record<string, {
    status: 'dirty' | 'saving' | 'saved' | 'error'
    message?: string
    savedAt?: string
  }>
  addPendingTask: (taskId: string, paperInput: PaperInput) => void
  updateTaskContent: (id: string, data: Partial<Omit<Task, 'id' | 'createdAt' | 'kind'>>) => void
  applyTaskSnapshot: (snapshot: TaskSnapshot, paperInput?: PaperInput) => void
  updateTaskCollection: (id: string, collection: Partial<CollectionMeta>) => void
  saveTaskCollection: (id: string, collection?: CollectionMeta) => Promise<void>
  createCollectionFolder: (folder: string) => string
  deleteCollectionFolder: (folder: string) => Promise<void>
  loadSavedTasks: () => Promise<void>
  removeTask: (id: string) => Promise<void>
  clearTasks: () => void
  setCurrentTask: (taskId: string | null) => void
  recordReadingProgress: (
    taskId: string,
    location: Pick<WorkspaceLocation, 'view' | 'page'>,
  ) => void
  getCurrentTask: () => Task | null
  retryTask: (id: string) => void
}

const DEFAULT_COLLECTION: CollectionMeta = {
  folder: DEFAULT_COLLECTION_FOLDER,
  tags: [],
  note: '',
}

const collectionSyncTimers = new Map<string, ReturnType<typeof setTimeout>>()

export const migratePaperTaskState = (persisted: unknown) => {
  const state = (persisted || {}) as Partial<TaskStore>
  const tasks = Array.isArray(state.tasks)
    ? state.tasks.filter((task): task is Task => task?.kind === 'paper')
    : []
  return {
    ...state,
    tasks,
    currentTaskId: state.currentTaskId && tasks.some(task => task.id === state.currentTaskId)
      ? state.currentTaskId
      : null,
    collectionFolders: mergeCollectionFolders(
      Array.isArray(state.collectionFolders) ? state.collectionFolders : [],
      tasks.map(task => task.collection?.folder || DEFAULT_COLLECTION_FOLDER),
    ),
    collectionSync: {},
  }
}

const taskFromSnapshot = (snapshot: TaskSnapshot, previous?: Task, paperInput?: PaperInput): Task => ({
  id: snapshot.id,
  kind: 'paper',
  status: snapshot.status,
  title: snapshot.title || snapshot.paperDocument?.title || previous?.title || '未命名论文',
  paperInput: {
    ...previous?.paperInput,
    ...snapshot.paperInput,
    ...paperInput,
  },
  paperDocument: snapshot.paperDocument || previous?.paperDocument,
  insights: snapshot.insights || previous?.insights,
  collection: snapshot.collection || previous?.collection || DEFAULT_COLLECTION,
  message: snapshot.message,
  error: snapshot.error,
  createdAt: snapshot.createdAt || previous?.createdAt || new Date().toISOString(),
  updatedAt: snapshot.updatedAt || previous?.updatedAt,
  readingProgress: previous?.readingProgress,
})

export const useTaskStore = create<TaskStore>()(
  persist(
    (setState, getState) => ({
      tasks: [],
      currentTaskId: null,
      collectionFolders: [DEFAULT_COLLECTION_FOLDER],
      collectionSync: {},

      addPendingTask: (taskId, paperInput) => setState(state => ({
        tasks: [
          {
            id: taskId,
            kind: 'paper',
            status: 'PENDING',
            title: paperInput.filename || paperInput.source_url || '正在导入论文',
            paperInput,
            collection: DEFAULT_COLLECTION,
            createdAt: new Date().toISOString(),
          },
          ...state.tasks.filter(task => task.id !== taskId),
        ],
        currentTaskId: taskId,
      })),

      updateTaskContent: (id, data) => setState(state => ({
        tasks: state.tasks.map(task => task.id === id ? { ...task, ...data } : task),
      })),

      applyTaskSnapshot: (snapshot, paperInput) => setState(state => {
        const previous = state.tasks.find(task => task.id === snapshot.id)
        const next = taskFromSnapshot(snapshot, previous, paperInput)
        return {
          tasks: [next, ...state.tasks.filter(task => task.id !== snapshot.id)],
          currentTaskId: snapshot.id,
          collectionFolders: mergeCollectionFolders(
            state.collectionFolders,
            [next.collection.folder],
          ),
        }
      }),

      loadSavedTasks: async () => {
        const snapshots = await list_generated_tasks()
        setState(state => {
          const previousById = new Map(state.tasks.map(task => [task.id, task]))
          const tasks = snapshots
            .map(snapshot => taskFromSnapshot(snapshot, previousById.get(snapshot.id)))
            .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
          const currentTaskId = state.currentTaskId && tasks.some(task => task.id === state.currentTaskId)
            ? state.currentTaskId
            : null
          return {
            tasks,
            currentTaskId,
            collectionFolders: mergeCollectionFolders(
              state.collectionFolders,
              tasks.map(task => task.collection.folder),
            ),
          }
        })
      },

      createCollectionFolder: folder => {
        const normalized = normalizeCollectionFolder(folder)
        const validationError = validateCollectionFolder(normalized)
        if (validationError) throw new Error(validationError)
        const knownFolders = mergeCollectionFolders(
          getState().collectionFolders,
          getState().tasks.map(task => task.collection.folder),
        )
        if (knownFolders.some(item => collectionFolderKey(item) === collectionFolderKey(normalized))) {
          throw new Error('收藏夹名称已存在')
        }
        setState({ collectionFolders: mergeCollectionFolders([...knownFolders, normalized]) })
        return normalized
      },

      deleteCollectionFolder: async folder => {
        const normalized = normalizeCollectionFolder(folder)
        const validationError = validateCollectionFolder(normalized)
        if (validationError) throw new Error(validationError)
        if (collectionFolderKey(normalized) === collectionFolderKey(DEFAULT_COLLECTION_FOLDER)) {
          throw new Error('默认收藏夹不能删除')
        }

        try {
          await delete_collection_folder(normalized)
          const affectedTaskIds = new Set(
            getState().tasks
              .filter(task => collectionFolderKey(task.collection.folder) === collectionFolderKey(normalized))
              .map(task => task.id),
          )
          setState(state => ({
            tasks: state.tasks.map(task => affectedTaskIds.has(task.id)
              ? { ...task, collection: { ...task.collection, folder: DEFAULT_COLLECTION_FOLDER } }
              : task),
            collectionFolders: state.collectionFolders.filter(
              item => collectionFolderKey(item) !== collectionFolderKey(normalized),
            ),
            collectionSync: Object.fromEntries(
              Object.entries(state.collectionSync).filter(([taskId]) => !affectedTaskIds.has(taskId)),
            ),
          }))
          toast.success(affectedTaskIds.size
            ? `收藏夹已删除，${affectedTaskIds.size} 篇论文已移回默认收藏夹`
            : '收藏夹已删除')
        }
        catch (error) {
          toast.error('收藏夹删除失败，未更改本地分类')
          throw error
        }
      },

      updateTaskCollection: (id, collection) => {
        setState(state => ({
          tasks: state.tasks.map(task => task.id === id
            ? { ...task, collection: { ...task.collection, ...collection } }
            : task),
          collectionSync: {
            ...state.collectionSync,
            [id]: { status: 'dirty', message: '有未保存的收藏信息' },
          },
        }))
        const timer = collectionSyncTimers.get(id)
        if (timer) clearTimeout(timer)
        collectionSyncTimers.set(id, setTimeout(() => {
          void getState().saveTaskCollection(id).catch(() => undefined)
        }, 800))
      },

      saveTaskCollection: async (id, collection) => {
        const timer = collectionSyncTimers.get(id)
        if (timer) clearTimeout(timer)
        collectionSyncTimers.delete(id)
        const task = getState().tasks.find(item => item.id === id)
        if (!task) throw new Error('论文不存在')
        const normalizedFolder = normalizeCollectionFolder(collection?.folder ?? task.collection.folder)
        const validationError = validateCollectionFolder(normalizedFolder)
        if (validationError) {
          setState(state => ({
            collectionSync: { ...state.collectionSync, [id]: { status: 'error', message: validationError } },
          }))
          throw new Error(validationError)
        }
        const nextCollection: CollectionMeta = {
          ...(collection || task.collection),
          folder: normalizedFolder,
          tags: Array.from(new Set((collection?.tags ?? task.collection.tags).map(tag => tag.trim()).filter(Boolean))),
          note: collection?.note ?? task.collection.note,
        }
        setState(state => ({
          collectionSync: { ...state.collectionSync, [id]: { status: 'saving', message: '正在保存收藏信息' } },
        }))
        try {
          await update_task_collection({
            task_id: id,
            collection_folder: nextCollection.folder,
            collection_tags: nextCollection.tags,
            collection_note: nextCollection.note,
          })
          setState(state => ({
            tasks: state.tasks.map(item => item.id === id
              ? { ...item, collection: nextCollection }
              : item),
            collectionFolders: mergeCollectionFolders(state.collectionFolders, [nextCollection.folder]),
            collectionSync: {
              ...state.collectionSync,
              [id]: { status: 'saved', message: '收藏信息已保存', savedAt: new Date().toISOString() },
            },
          }))
          toast.success('收藏夹和标签已保存')
        }
        catch (error) {
          const message = error instanceof Error ? error.message : '收藏信息保存失败'
          setState(state => ({
            collectionSync: { ...state.collectionSync, [id]: { status: 'error', message } },
          }))
          toast.error('收藏信息保存失败，可在资料库重试')
          throw error
        }
      },

      getCurrentTask: () => {
        const currentTaskId = getState().currentTaskId
        return getState().tasks.find(task => task.id === currentTaskId) || null
      },

      retryTask: () => {
        toast('请重新导入原 PDF 或论文 URL，失败任务不会复用不完整产物。')
      },

      removeTask: async id => {
        const previousTasks = getState().tasks
        const previousCurrentTaskId = getState().currentTaskId
        setState(state => ({
          tasks: state.tasks.filter(task => task.id !== id),
          currentTaskId: state.currentTaskId === id ? null : state.currentTaskId,
        }))
        try {
          await delete_paper(id)
        }
        catch (error) {
          setState({ tasks: previousTasks, currentTaskId: previousCurrentTaskId })
          throw error
        }
      },

      clearTasks: () => setState({ tasks: [], currentTaskId: null }),
      setCurrentTask: currentTaskId => setState({ currentTaskId }),
      recordReadingProgress: (taskId, location) => setState(state => ({
        tasks: state.tasks.map(task => task.id === taskId
          ? { ...task, readingProgress: updateWorkspaceResumeState(task.readingProgress, location) }
          : task),
      })),
    }),
    {
      name: 'fastread-paper-task-storage',
      version: 4,
      migrate: migratePaperTaskState,
      partialize: state => ({
        tasks: state.tasks,
        currentTaskId: state.currentTaskId,
        collectionFolders: state.collectionFolders,
      }) as TaskStore,
      storage: createJSONStorage(() => ({
        getItem: async name => (await get(name)) ?? null,
        setItem: async (name, value) => { await set(name, value) },
        removeItem: async name => { await del(name) },
      })),
    },
  ),
)
