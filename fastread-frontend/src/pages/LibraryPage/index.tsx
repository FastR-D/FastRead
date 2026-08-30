import { useLayoutEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  BookOpenCheck,
  Check,
  Circle,
  Clock3,
  FolderCog,
  FolderOpen,
  Grid2X2,
  List,
  Loader2,
  Plus,
  Search,
  SearchCheck,
  Save,
  Settings,
  ShieldCheck,
  Tags,
  Trash2,
} from 'lucide-react'
import logo from '@/assets/icon.png'
import { useTaskStore, type CollectionMeta, type Task } from '@/store/taskStore'
import { cn } from '@/lib/utils'
import {
  buildWorkspaceSearch,
  compareReadingRecency,
  workspaceLocationFromResume,
} from '@/utils/workspaceNavigation'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DEFAULT_COLLECTION_FOLDER,
  mergeCollectionFolders,
  normalizeCollectionFolder,
  validateCollectionFolder,
} from '@/utils/collections'

type LibraryFilter = 'papers'
type ViewMode = 'grid' | 'list'
const ALL_COLLECTIONS = ''

function getNotebookTitle(task: Task) { return task.title || task.paperDocument?.title || '未命名论文' }

function getSourceLabel(task: Task) {
  const pages = task.paperDocument?.page_count || task.paperDocument?.pages.length || 0
  return pages ? `${pages} 页原文` : '等待分页原文'
}

function formatDate(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date
    .toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
    .replace(/\s/g, '')
}

function formatRelativeTime(value?: string) {
  if (!value) return ''
  const openedAt = new Date(value).getTime()
  if (!Number.isFinite(openedAt)) return ''
  const minutes = Math.max(0, Math.floor((Date.now() - openedAt) / 60000))
  if (minutes < 1) return '刚刚打开'
  if (minutes < 60) return `${minutes} 分钟前打开`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前打开`
  return `${Math.floor(hours / 24)} 天前打开`
}

function resumeLabel(task: Task) {
  const progress = task.readingProgress
  if (!progress) return '继续阅读'
  if (progress.view === 'source') return progress.page ? `继续第 ${progress.page} 页` : '继续阅读原文'
  if (progress.view === 'report') return '继续查看阅读报告'
  if (progress.view === 'related') return '继续查看近邻论文'
  if (progress.view === 'summary') return '继续写个人总结'
  if (progress.view === 'chat') return '继续带页码追问'
  return '继续阅读'
}

function VerdictMark({ task }: { task: Task }) {
  const report = task.insights?.reading_report
  const summary = task.insights?.personal_summary?.content
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-sm px-2 py-1 text-xs', summary ? 'bg-emerald-50 text-emerald-700' : report ? 'bg-blue-50 text-blue-700' : 'bg-slate-100 text-slate-600')}>
      <BookOpen className="h-3 w-3" />
      {summary ? '总结已完成' : report ? '报告已生成' : '待生成报告'}
    </span>
  )
}

function FlatPattern({ index }: { index: number }) {
  const palettes = [
    'bg-slate-50 text-slate-700',
    'bg-emerald-50 text-emerald-800',
    'bg-blue-50 text-blue-800',
    'bg-amber-50 text-amber-800',
    'bg-red-50 text-red-800',
    'bg-neutral-50 text-neutral-800',
  ]
  const Icon = [SearchCheck, ShieldCheck, AlertCircle, Check, BookOpen, Circle][index % 6]
  return (
    <div className={cn('absolute inset-0', palettes[index % palettes.length])}>
      <Icon className="absolute left-7 top-6 h-9 w-9 opacity-70" />
      <div className="absolute bottom-6 right-7 h-20 w-20 rounded-sm border border-black/10" />
      <div className="absolute right-24 top-10 h-7 w-24 rounded-sm border border-black/10" />
      <div className="absolute bottom-12 left-10 h-1.5 w-32 rounded-sm bg-black/10" />
    </div>
  )
}

function RecentNotebookCard({
  task,
  index,
  viewMode,
  onOpen,
  onDelete,
  onEditCollection,
}: {
  task: Task
  index: number
  viewMode: ViewMode
  onOpen: (taskId: string) => void
  onDelete: (task: Task) => void
  onEditCollection: (task: Task) => void
}) {
  const image = ''
  const tags = task.collection?.tags || []
  const folder = task.collection?.folder || '默认收藏夹'
  const NotebookIcon = [SearchCheck, ShieldCheck, AlertCircle, Check, BookOpen, Circle][index % 6]

  if (viewMode === 'list') {
    return (
      <div className="flex min-h-24 w-full items-center gap-3 rounded-lg border border-neutral-200 bg-white px-4 py-3 transition hover:border-neutral-300 hover:bg-neutral-50">
        <button
          type="button"
          onClick={() => onOpen(task.id)}
          className="flex min-w-0 flex-1 items-center gap-4 text-left outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <div className="relative h-16 w-24 shrink-0 overflow-hidden rounded-md bg-neutral-100">
            {image ? (
              <img src={image} alt="" referrerPolicy="no-referrer" className="h-full w-full object-cover" />
            ) : (
              <FlatPattern index={index} />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="line-clamp-1 text-base font-medium text-neutral-950">
              {getNotebookTitle(task)}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-neutral-500">
              <span>{formatDate(task.readingProgress?.lastOpenedAt || task.createdAt)} · {getSourceLabel(task)}</span>
              <span className="inline-flex items-center gap-1 text-xs"><FolderOpen className="h-3 w-3" />{folder}</span>
            </div>
          </div>
        </button>
        <VerdictMark task={task} />
        <button
          type="button"
          onClick={() => onEditCollection(task)}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-neutral-500 transition hover:bg-blue-50 hover:text-blue-700 focus-visible:ring-2 focus-visible:ring-blue-500"
          aria-label={`管理收藏信息：${getNotebookTitle(task)}`}
          title="收藏夹与标签"
        >
          <FolderCog className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() => onDelete(task)}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-neutral-500 transition hover:bg-rose-50 hover:text-rose-600 focus-visible:ring-2 focus-visible:ring-rose-500"
          aria-label={`删除阅读任务：${getNotebookTitle(task)}`}
          title="删除"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    )
  }

  return (
    <div
      className="group relative h-[168px] overflow-hidden rounded-lg border border-transparent text-left outline-none transition hover:-translate-y-0.5 hover:shadow-md focus-visible:ring-2 focus-visible:ring-primary"
    >
      <button
        type="button"
        onClick={() => onEditCollection(task)}
        className={cn(
          'absolute right-14 top-3 z-20 flex h-10 w-10 items-center justify-center rounded-full opacity-0 transition focus-visible:opacity-100 focus-visible:ring-2 group-hover:opacity-100',
          image ? 'bg-black/35 text-white hover:bg-blue-600 focus-visible:ring-white' : 'bg-white/75 text-neutral-600 hover:bg-blue-50 hover:text-blue-700 focus-visible:ring-blue-500',
        )}
        aria-label={`管理收藏信息：${getNotebookTitle(task)}`}
        title="收藏夹与标签"
      >
        <FolderCog className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={() => onOpen(task.id)}
        className="absolute inset-0 z-10"
        aria-label={`打开阅读任务：${getNotebookTitle(task)}`}
      />
      {image ? (
        <>
          <img
            src={image}
            alt=""
            referrerPolicy="no-referrer"
            className="absolute inset-0 h-full w-full object-cover transition duration-300 group-hover:scale-[1.03]"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/25 to-black/5" />
        </>
      ) : (
        <FlatPattern index={index} />
      )}
      <button
        type="button"
        onClick={() => onDelete(task)}
        className={cn(
          'absolute right-3 top-3 z-20 flex h-10 w-10 items-center justify-center rounded-full opacity-0 transition focus-visible:opacity-100 focus-visible:ring-2 group-hover:opacity-100',
          image
            ? 'bg-black/35 text-white hover:bg-rose-600 focus-visible:ring-white'
            : 'bg-white/75 text-neutral-600 hover:bg-rose-50 hover:text-rose-600 focus-visible:ring-rose-500'
        )}
        aria-label={`删除阅读任务：${getNotebookTitle(task)}`}
        title="删除"
      >
        <Trash2 className="h-4 w-4" />
      </button>
      <div className={cn('pointer-events-none relative z-10 flex h-full flex-col p-5', image ? 'text-white' : 'text-neutral-950')}>
        <div className="flex items-start justify-between gap-3">
          <span className={cn('flex h-9 w-9 items-center justify-center rounded-full', image ? 'bg-white/18' : 'bg-white/60')}>
            <NotebookIcon className={cn('h-4 w-4', image ? 'text-white' : 'text-neutral-700')} />
          </span>
        </div>
        <div className="mt-auto">
          <h3 className="line-clamp-2 text-xl font-medium leading-snug">{getNotebookTitle(task)}</h3>
          <div className={cn('mt-3 text-sm', image ? 'text-white/82' : 'text-neutral-600')}>
            {formatDate(task.readingProgress?.lastOpenedAt || task.createdAt)} · {getSourceLabel(task)}
          </div>
          {tags.length > 0 && (
            <div className={cn('mt-2 flex items-center gap-1 text-xs', image ? 'text-white/75' : 'text-neutral-500')}>
              <Tags className="h-3 w-3" />
              <span className="truncate">{tags.slice(0, 3).join('，')}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function NewNotebookCard({ onCreate }: { onCreate: () => void }) {
  return (
    <button
      type="button"
      onClick={onCreate}
      className="flex h-[168px] flex-col items-center justify-center rounded-lg border border-neutral-200 bg-white text-neutral-900 transition hover:border-neutral-300 hover:bg-neutral-50 focus-visible:ring-2 focus-visible:ring-primary"
    >
      <span className="flex h-16 w-16 items-center justify-center rounded-full bg-[#eef1ff] text-primary">
        <Plus className="h-7 w-7" />
      </span>
      <span className="mt-4 text-lg font-medium">导入 PDF / 论文 URL</span>
    </button>
  )
}

export default function LibraryPage() {
  const navigate = useNavigate()
  const tasks = useTaskStore(state => state.tasks)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const removeTask = useTaskStore(state => state.removeTask)
  const saveTaskCollection = useTaskStore(state => state.saveTaskCollection)
  const collectionFolders = useTaskStore(state => state.collectionFolders || [])
  const createCollectionFolder = useTaskStore(state => state.createCollectionFolder)
  const deleteCollectionFolder = useTaskStore(state => state.deleteCollectionFolder)
  const collectionSync = useTaskStore(state => state.collectionSync || {})
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<LibraryFilter>('papers')
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [taskToDelete, setTaskToDelete] = useState<Task | null>(null)
  const [deletingTaskId, setDeletingTaskId] = useState<string | null>(null)
  const [folderFilter, setFolderFilter] = useState(ALL_COLLECTIONS)
  const [tagFilter, setTagFilter] = useState('all')
  const [collectionTaskId, setCollectionTaskId] = useState<string | null>(null)
  const [collectionDraft, setCollectionDraft] = useState<CollectionMeta | null>(null)
  const [collectionTagsDraft, setCollectionTagsDraft] = useState('')
  const [collectionError, setCollectionError] = useState('')
  const [newFolderOpen, setNewFolderOpen] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [newFolderError, setNewFolderError] = useState('')
  const [folderToDelete, setFolderToDelete] = useState<string | null>(null)
  const [deletingFolder, setDeletingFolder] = useState(false)

  useLayoutEffect(() => {
    document.documentElement.classList.add('document-scroll')
    return () => document.documentElement.classList.remove('document-scroll')
  }, [])

  const collectionTask = tasks.find(task => task.id === collectionTaskId) || null
  const collectionState = collectionTask ? collectionSync[collectionTask.id] : undefined

  const sortedTasks = useMemo(
    () => [...tasks].sort(compareReadingRecency),
    [tasks]
  )

  const continueTask = useMemo(
    () => sortedTasks.find(task => Boolean(task.paperDocument) && Boolean(task.readingProgress)),
    [sortedTasks]
  )

  const folders = useMemo(
    () => mergeCollectionFolders(
      collectionFolders,
      tasks.map(task => task.collection?.folder || DEFAULT_COLLECTION_FOLDER),
    ),
    [collectionFolders, tasks],
  )
  const availableTags = useMemo(
    () => Array.from(new Set(tasks.flatMap(task => task.collection?.tags || []))).sort(),
    [tasks],
  )

  const searchedTasks = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return sortedTasks
    return sortedTasks.filter(task => {
      const target = [
        getNotebookTitle(task),
        task.paperInput.source_url,
        task.paperDocument?.authors?.join(' '),
        task.paperDocument?.venue?.short_name,
        task.collection?.folder,
        ...(task.collection?.tags || []),
        task.collection?.note,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return target.includes(keyword)
    })
  }, [query, sortedTasks])

  const visibleTasks = useMemo(() => {
    const collectionFiltered = searchedTasks.filter(task => {
      if (folderFilter !== ALL_COLLECTIONS && (task.collection?.folder || DEFAULT_COLLECTION_FOLDER) !== folderFilter) return false
      if (tagFilter !== 'all' && !(task.collection?.tags || []).includes(tagFilter)) return false
      return true
    })
    return collectionFiltered
  }, [folderFilter, searchedTasks, tagFilter])

  const openTask = (taskId: string) => {
    const task = tasks.find(item => item.id === taskId)
    const location = workspaceLocationFromResume(taskId, task?.readingProgress, 'source')
    setCurrentTask(taskId)
    navigate(`/workspace?${buildWorkspaceSearch(location)}`)
  }

  const createTask = () => {
    setCurrentTask(null)
    navigate('/workspace?view=source')
  }

  const confirmDeleteTask = async () => {
    if (!taskToDelete) return

    setDeletingTaskId(taskToDelete.id)
    try {
      await removeTask(taskToDelete.id)
      setTaskToDelete(null)
    } catch {
      // delete_task already shows the error toast; keep the dialog open so users can retry.
    } finally {
      setDeletingTaskId(null)
    }
  }

  const openCollectionEditor = (task: Task) => {
    setCollectionTaskId(task.id)
    setCollectionDraft({
      folder: task.collection?.folder || DEFAULT_COLLECTION_FOLDER,
      tags: [...(task.collection?.tags || [])],
      note: task.collection?.note || '',
    })
    setCollectionTagsDraft((task.collection?.tags || []).join('，'))
    setCollectionError('')
  }

  const closeCollectionEditor = () => {
    setCollectionTaskId(null)
    setCollectionDraft(null)
    setCollectionTagsDraft('')
    setCollectionError('')
  }

  const saveCollectionDraft = async () => {
    if (!collectionTask || !collectionDraft) return
    const folder = normalizeCollectionFolder(collectionDraft.folder)
    const validationError = validateCollectionFolder(folder)
    if (validationError) {
      setCollectionError(validationError)
      return
    }
    const nextCollection = {
      ...collectionDraft,
      folder,
      tags: collectionTagsDraft
        .split(/[，,\n]+/u)
        .map(tag => tag.trim())
        .filter(Boolean),
    }
    setCollectionError('')
    try {
      await saveTaskCollection(collectionTask.id, nextCollection)
      closeCollectionEditor()
    }
    catch (error) {
      setCollectionError(error instanceof Error ? error.message : '收藏信息保存失败')
    }
  }

  const createFolder = () => {
    try {
      const normalized = createCollectionFolder(newFolderName)
      setFolderFilter(normalized)
      setNewFolderName('')
      setNewFolderError('')
      setNewFolderOpen(false)
    }
    catch (error) {
      setNewFolderError(error instanceof Error ? error.message : '新建收藏夹失败')
    }
  }

  const confirmDeleteFolder = async () => {
    if (!folderToDelete) return
    setDeletingFolder(true)
    try {
      await deleteCollectionFolder(folderToDelete)
      setFolderFilter(ALL_COLLECTIONS)
      setFolderToDelete(null)
    }
    catch {
      // Store keeps both the directory and paper assignments unchanged on failure.
    }
    finally {
      setDeletingFolder(false)
    }
  }

  const tabs: Array<{ id: LibraryFilter; label: string }> = [
    { id: 'papers', label: '论文' },
  ]

  return (
    <div className="min-h-screen bg-white text-neutral-950">
      <header className="sticky top-0 z-20 flex h-16 items-center justify-between bg-white/95 px-7 backdrop-blur">
        <Link to="/" className="flex items-center gap-3">
          <img src={logo} alt="FastRead" className="h-9 w-9 rounded-md" />
          <span className="text-2xl font-semibold tracking-normal">FastRead</span>
        </Link>
        <div className="flex items-center gap-3">
          <Link
            to="/search"
            className="inline-flex h-10 items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-4 text-sm font-medium text-emerald-800 transition hover:bg-emerald-100"
          >
            <Search className="h-4 w-4" />
            论文检索
          </Link>
          <Link
            to="/research"
            className="inline-flex h-10 items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-4 text-sm font-medium text-blue-800 transition hover:bg-blue-100"
          >
            <BookOpenCheck className="h-4 w-4" />
            专题知识库
          </Link>
          <Link
            to="/settings"
            className="inline-flex h-10 items-center gap-2 rounded-full border border-neutral-200 px-4 text-sm font-medium text-neutral-900 transition hover:bg-neutral-50"
          >
            <Settings className="h-4 w-4" />
            设置
          </Link>
          <button
            type="button"
            onClick={createTask}
            className="inline-flex h-10 items-center gap-2 rounded-full bg-black px-5 text-sm font-medium text-white transition hover:bg-neutral-800"
          >
            <Plus className="h-4 w-4" />
            导入论文
          </button>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-[1640px] flex-col gap-12 px-8 pb-16 pt-8 lg:px-14">
        {continueTask && (
          <section className="flex flex-col gap-5 rounded-2xl border border-blue-100 bg-gradient-to-r from-blue-50 via-white to-indigo-50 px-6 py-5 shadow-sm sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-blue-700">
                <Clock3 className="h-4 w-4" />
                继续阅读
              </div>
              <h2 className="mt-2 truncate text-xl font-semibold text-neutral-950">
                {getNotebookTitle(continueTask)}
              </h2>
              <p className="mt-1 text-sm text-neutral-600">
                {formatRelativeTime(continueTask.readingProgress?.lastOpenedAt)}
                {continueTask.readingProgress?.page ? ` · 上次读到第 ${continueTask.readingProgress.page} 页` : ''}
              </p>
            </div>
            <button
              type="button"
              onClick={() => openTask(continueTask.id)}
              className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-full bg-neutral-950 px-5 text-sm font-semibold text-white transition hover:bg-neutral-800 focus-visible:ring-2 focus-visible:ring-blue-600"
            >
              {resumeLabel(continueTask)}
              <ArrowRight className="h-4 w-4" />
            </button>
          </section>
        )}

        <section className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            {tabs.map(tab => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setFilter(tab.id)}
                className={cn(
                  'h-12 rounded-full px-5 text-sm transition',
                  filter === tab.id
                    ? 'border border-neutral-300 bg-[#f0f2fb] text-neutral-950 shadow-sm'
                    : 'text-neutral-700 hover:bg-neutral-100'
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <div className="flex h-12 items-center gap-2 rounded-full border border-neutral-200 px-4">
              <Search className="h-5 w-5 text-neutral-500" />
              <input
                value={query}
                onChange={event => setQuery(event.target.value)}
                placeholder="搜索论文与报告"
                className="w-40 bg-transparent text-sm outline-none placeholder:text-neutral-400"
              />
            </div>
            <div className="flex h-12 overflow-hidden rounded-full border border-neutral-200">
              <button
                type="button"
                onClick={() => setViewMode('grid')}
                className={cn('flex w-14 items-center justify-center', viewMode === 'grid' ? 'bg-[#f0f2fb]' : 'hover:bg-neutral-50')}
                title="方格视图"
              >
                <Grid2X2 className="h-5 w-5" />
              </button>
              <button
                type="button"
                onClick={() => setViewMode('list')}
                className={cn('flex w-14 items-center justify-center border-l border-neutral-200', viewMode === 'list' ? 'bg-[#f0f2fb]' : 'hover:bg-neutral-50')}
                title="列表视图"
              >
                <List className="h-5 w-5" />
              </button>
            </div>
            <div className="inline-flex h-12 items-center gap-2 rounded-full border border-neutral-200 px-5 text-sm text-neutral-600">
              <Clock3 className="h-4 w-4" />
              最近打开
            </div>
          </div>
        </section>

        <section className="flex flex-wrap items-center gap-3 rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-800">
            <FolderOpen className="h-4 w-4" />
            收藏目录
          </div>
          <label className="flex items-center gap-2 text-xs text-neutral-500">
            收藏夹
            <select value={folderFilter} onChange={event => setFolderFilter(event.target.value)} className="h-9 rounded-md border border-neutral-200 bg-white px-3 text-sm text-neutral-800">
              <option value={ALL_COLLECTIONS}>全部收藏夹</option>
              {folders.map(folder => <option key={folder} value={folder}>{folder}</option>)}
            </select>
          </label>
          <Button
            type="button"
            variant="outline"
            className="h-9"
            onClick={() => {
              setNewFolderName('')
              setNewFolderError('')
              setNewFolderOpen(true)
            }}
          >
            <Plus className="h-4 w-4" />新建收藏夹
          </Button>
          {folderFilter !== ALL_COLLECTIONS && folderFilter !== DEFAULT_COLLECTION_FOLDER && (
            <Button
              type="button"
              variant="outline"
              className="h-9 text-rose-700 hover:bg-rose-50 hover:text-rose-800"
              onClick={() => setFolderToDelete(folderFilter)}
            >
              <Trash2 className="h-4 w-4" />删除当前收藏夹
            </Button>
          )}
          <label className="flex items-center gap-2 text-xs text-neutral-500">
            标签
            <select value={tagFilter} onChange={event => setTagFilter(event.target.value)} className="h-9 rounded-md border border-neutral-200 bg-white px-3 text-sm text-neutral-800">
              <option value="all">全部标签</option>
              {availableTags.map(tag => <option key={tag} value={tag}>{tag}</option>)}
            </select>
          </label>
          {(folderFilter !== ALL_COLLECTIONS || tagFilter !== 'all') && (
            <button type="button" onClick={() => { setFolderFilter(ALL_COLLECTIONS); setTagFilter('all') }} className="text-xs text-blue-700 underline underline-offset-2">
              清除分类筛选
            </button>
          )}
          <span className="ml-auto text-xs text-neutral-500">{visibleTasks.length} 条匹配记录</span>
        </section>

        <section>
          <h2 className="mb-5 text-3xl font-medium tracking-normal">
            {query.trim() ? '搜索结果' : '最近阅读'}
          </h2>
          {viewMode === 'grid' ? (
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
              <NewNotebookCard onCreate={createTask} />
              {visibleTasks.map((task, index) => (
                <RecentNotebookCard
                  key={task.id}
                  task={task}
                  index={index}
                  viewMode={viewMode}
                  onOpen={openTask}
                  onDelete={setTaskToDelete}
                  onEditCollection={openCollectionEditor}
                />
              ))}
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <NewNotebookCard onCreate={createTask} />
              {visibleTasks.map((task, index) => (
                <RecentNotebookCard
                  key={task.id}
                  task={task}
                  index={index}
                  viewMode={viewMode}
                  onOpen={openTask}
                  onDelete={setTaskToDelete}
                  onEditCollection={openCollectionEditor}
                />
              ))}
            </div>
          )}

          {visibleTasks.length === 0 && (
            <div className="mt-6 rounded-lg border border-dashed border-neutral-300 py-16 text-center">
              <SearchCheck className="mx-auto h-10 w-10 text-neutral-300" />
              <p className="mt-4 text-base font-medium text-neutral-800">还没有匹配的论文</p>
              <p className="mt-2 text-sm text-neutral-500">导入 PDF 或论文 URL，分页原文与阅读报告会出现在这里。</p>
            </div>
          )}
        </section>
      </main>

      <Dialog open={Boolean(taskToDelete)} onOpenChange={open => !open && setTaskToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除这条阅读任务？</DialogTitle>
            <DialogDescription>
              将删除「{taskToDelete ? getNotebookTitle(taskToDelete) : ''}」以及对应的分页原文、阅读报告和本地证据索引，此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setTaskToDelete(null)}
              disabled={Boolean(deletingTaskId)}
            >
              取消
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={confirmDeleteTask}
              disabled={Boolean(deletingTaskId)}
            >
              {deletingTaskId ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  删除中
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4" />
                  删除
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(collectionTask)} onOpenChange={open => {
        if (!open && collectionState?.status !== 'saving') closeCollectionEditor()
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>收藏夹与标签</DialogTitle>
            <DialogDescription>
              「{collectionTask ? getNotebookTitle(collectionTask) : ''}」保存后可在资料库的收藏目录中单独筛选。
            </DialogDescription>
          </DialogHeader>
          {collectionTask && collectionDraft && (
            <div className="space-y-4 py-2">
              <label className="block text-sm font-medium text-neutral-800">
                收藏夹
                <input
                  value={collectionDraft.folder}
                  onChange={event => {
                    setCollectionDraft({ ...collectionDraft, folder: event.target.value })
                    setCollectionError('')
                  }}
                  list="collection-folder-options"
                  className="mt-1.5 h-10 w-full rounded-md border border-neutral-200 px-3 text-sm outline-none focus:border-blue-500"
                  placeholder="例如：大模型安全"
                />
                <datalist id="collection-folder-options">
                  {folders.map(folder => <option key={folder} value={folder} />)}
                </datalist>
                <span className="mt-1 block text-xs font-normal text-neutral-500">可选现有收藏夹，也可直接输入新名称。</span>
              </label>
              <label className="block text-sm font-medium text-neutral-800">
                标签
                <input
                  value={collectionTagsDraft}
                  onChange={event => setCollectionTagsDraft(event.target.value)}
                  className="mt-1.5 h-10 w-full rounded-md border border-neutral-200 px-3 text-sm outline-none focus:border-blue-500"
                  placeholder="例如：prompt-injection，survey"
                />
              </label>
              <label className="block text-sm font-medium text-neutral-800">
                归档备注
                <textarea
                  value={collectionDraft.note}
                  onChange={event => setCollectionDraft({ ...collectionDraft, note: event.target.value })}
                  className="mt-1.5 min-h-24 w-full resize-y rounded-md border border-neutral-200 px-3 py-2 text-sm outline-none focus:border-blue-500"
                  placeholder="记录为什么收藏、后续要读什么"
                />
              </label>
              {collectionDraft.folder !== DEFAULT_COLLECTION_FOLDER && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setCollectionDraft({ ...collectionDraft, folder: DEFAULT_COLLECTION_FOLDER })
                    setCollectionError('')
                  }}
                >
                  移出当前收藏夹
                </Button>
              )}
              <div className={cn(
                'rounded-md border px-3 py-2 text-xs',
                collectionError || collectionState?.status === 'error'
                  ? 'border-red-200 bg-red-50 text-red-700'
                  : 'border-slate-200 bg-slate-50 text-slate-600',
              )}>
                {collectionError || collectionState?.message || '修改仅在点击“保存”后生效，取消不会改动原收藏信息。'}
              </div>
            </div>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={collectionState?.status === 'saving'}
              onClick={closeCollectionEditor}
            >
              取消
            </Button>
            <Button
              type="button"
              disabled={!collectionTask || !collectionDraft || collectionState?.status === 'saving'}
              onClick={() => void saveCollectionDraft()}
            >
              {collectionState?.status === 'saving' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={newFolderOpen} onOpenChange={open => {
        setNewFolderOpen(open)
        if (!open) {
          setNewFolderName('')
          setNewFolderError('')
        }
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建收藏夹</DialogTitle>
            <DialogDescription>新建后会保留在收藏目录中，即使暂时没有论文。</DialogDescription>
          </DialogHeader>
          <label className="block py-2 text-sm font-medium text-neutral-800">
            收藏夹名称
            <input
              autoFocus
              value={newFolderName}
              onChange={event => {
                setNewFolderName(event.target.value)
                setNewFolderError('')
              }}
              onKeyDown={event => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  createFolder()
                }
              }}
              className="mt-1.5 h-10 w-full rounded-md border border-neutral-200 px-3 text-sm outline-none focus:border-blue-500"
              placeholder="例如：本周必读"
            />
          </label>
          {newFolderError && <p className="text-sm text-red-700">{newFolderError}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setNewFolderOpen(false)}>取消</Button>
            <Button type="button" onClick={createFolder}>创建</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(folderToDelete)} onOpenChange={open => !open && !deletingFolder && setFolderToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除收藏夹？</DialogTitle>
            <DialogDescription>
              收藏夹“{folderToDelete || ''}”会被删除，其中论文将移回“{DEFAULT_COLLECTION_FOLDER}”，论文本身不会删除。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" disabled={deletingFolder} onClick={() => setFolderToDelete(null)}>取消</Button>
            <Button type="button" variant="destructive" disabled={deletingFolder} onClick={() => void confirmDeleteFolder()}>
              {deletingFolder ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
