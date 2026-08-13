import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  BookOpen,
  Check,
  ChevronDown,
  Circle,
  Grid2X2,
  List,
  Loader2,
  Plus,
  Search,
  SearchCheck,
  Settings,
  ShieldCheck,
  Tags,
  Trash2,
} from 'lucide-react'
import logo from '@/assets/icon.png'
import { useTaskStore, type Task } from '@/store/taskStore'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

type LibraryFilter = 'all' | 'mine' | 'featured'
type ViewMode = 'grid' | 'list'

const apiBase = () => String(import.meta.env.VITE_API_BASE_URL || 'api').replace(/\/$/, '')

function coverUrl(task: Task) {
  const rawCover = task.audioMeta?.cover_url
  if (!rawCover) return ''
  return `${apiBase()}/image_proxy?url=${encodeURIComponent(rawCover)}`
}

function getNotebookTitle(task: Task) {
  return task.audioMeta?.title || task.formData?.video_url || task.collection?.note || '联网核实任务'
}

function getSourceCount(task: Task) {
  const verification = task.insights?.verification
  const claimSourceUrls = new Set(
    (verification?.claims || [])
      .flatMap(claim => claim.online?.sources || [])
      .map(source => source.canonical_url || source.url)
      .filter(Boolean)
  )
  return verification?.sources?.length || claimSourceUrls.size
}

function isFirstClassVerificationTask(task: Task) {
  return task.platform === 'verification' || ['text', 'url'].includes(task.formData?.input_mode || '')
}

function isUnverifiedLegacyTask(task: Task) {
  return task.status === 'SUCCESS' && !task.insights?.verification && !isFirstClassVerificationTask(task)
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

function statusLabel(task: Task) {
  if (task.status === 'SUCCESS') return '已完成'
  if (task.status === 'FAILED') return '核实失败'
  return '核实中'
}

const verdictLabel: Record<string, string> = {
  supported: '支持',
  refuted: '反证',
  mixed: '混合',
  insufficient: '证据不足',
  data_void: '数据空缺',
  source_risk: '信源风险',
}

const verdictTone: Record<string, string> = {
  supported: 'bg-emerald-50 text-emerald-700',
  refuted: 'bg-red-50 text-red-700',
  mixed: 'bg-amber-50 text-amber-700',
  insufficient: 'bg-slate-100 text-slate-600',
  data_void: 'bg-orange-50 text-orange-700',
  source_risk: 'bg-red-50 text-red-700',
}

function VerdictMark({ task }: { task: Task }) {
  const verification = task.insights?.verification
  const status = verification?.overall?.status
  if (!status && isUnverifiedLegacyTask(task)) {
    return (
      <span className="inline-flex items-center gap-1 rounded-sm bg-amber-50 px-2 py-1 text-xs text-amber-700">
        <SearchCheck className="h-3 w-3" />
        未联网核实
      </span>
    )
  }
  if (!status) return <StatusMark task={task} />

  return (
    <span className={cn('inline-flex items-center gap-1 rounded-sm px-2 py-1 text-xs', verdictTone[status] || 'bg-slate-100 text-slate-600')}>
      <ShieldCheck className="h-3 w-3" />
      {verdictLabel[status] || status}
      <span className="font-mono opacity-70">
        {verification.claim_counts?.online_supported ?? 0}/{verification.claim_counts?.online_refuted ?? 0}/{verification.claim_counts?.total ?? 0}
      </span>
    </span>
  )
}

function StatusMark({ task }: { task: Task }) {
  if (task.status === 'SUCCESS') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-700">
        <Check className="h-3 w-3" />
        {statusLabel(task)}
      </span>
    )
  }
  if (task.status === 'FAILED') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2 py-1 text-xs text-rose-700">
        <AlertCircle className="h-3 w-3" />
        {statusLabel(task)}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-sky-50 px-2 py-1 text-xs text-sky-700">
      <Loader2 className="h-3 w-3 animate-spin" />
      {statusLabel(task)}
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
}: {
  task: Task
  index: number
  viewMode: ViewMode
  onOpen: (taskId: string) => void
  onDelete: (task: Task) => void
}) {
  const image = coverUrl(task)
  const tags = task.collection?.tags || []
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
            <div className="mt-1 text-sm text-neutral-500">
              {formatDate(task.createdAt)} · {getSourceCount(task)} 个来源
            </div>
          </div>
        </button>
        <VerdictMark task={task} />
        <button
          type="button"
          onClick={() => onDelete(task)}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-neutral-500 transition hover:bg-rose-50 hover:text-rose-600 focus-visible:ring-2 focus-visible:ring-rose-500"
          aria-label={`删除核验任务：${getNotebookTitle(task)}`}
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
        onClick={() => onOpen(task.id)}
        className="absolute inset-0 z-10"
        aria-label={`打开核验任务：${getNotebookTitle(task)}`}
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
        aria-label={`删除核验任务：${getNotebookTitle(task)}`}
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
            {formatDate(task.createdAt)} · {getSourceCount(task)} 个来源
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
      <span className="mt-4 text-lg font-medium">开始联网核实</span>
    </button>
  )
}

export default function LibraryPage() {
  const navigate = useNavigate()
  const tasks = useTaskStore(state => state.tasks)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const removeTask = useTaskStore(state => state.removeTask)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<LibraryFilter>('all')
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [taskToDelete, setTaskToDelete] = useState<Task | null>(null)
  const [deletingTaskId, setDeletingTaskId] = useState<string | null>(null)

  const sortedTasks = useMemo(
    () => [...tasks].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()),
    [tasks]
  )

  const searchedTasks = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return sortedTasks
    return sortedTasks.filter(task => {
      const target = [
        getNotebookTitle(task),
        task.formData?.video_url,
        task.insights?.verification?.overall?.status,
        isUnverifiedLegacyTask(task) ? '未联网核实' : '',
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
    if (filter === 'mine') {
      return searchedTasks.filter(task => {
        const verification = task.insights?.verification
        return (
          isUnverifiedLegacyTask(task) ||
          task.status === 'FAILED' ||
          Boolean(verification?.risk_flags?.length) ||
          ['refuted', 'mixed', 'insufficient', 'data_void', 'source_risk'].includes(verification?.overall?.status || '')
        )
      })
    }
    if (filter === 'featured') {
      return searchedTasks.filter(task => task.status === 'SUCCESS' && task.insights?.verification)
    }
    return searchedTasks
  }, [filter, searchedTasks])

  const openTask = (taskId: string) => {
    setCurrentTask(taskId)
    navigate('/workspace')
  }

  const createTask = () => {
    setCurrentTask(null)
    navigate('/workspace')
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

  const tabs: Array<{ id: LibraryFilter; label: string }> = [
    { id: 'all', label: '全部核验' },
    { id: 'mine', label: '需复核' },
    { id: 'featured', label: '已完成' },
  ]

  return (
    <div className="h-screen overflow-y-auto bg-white text-neutral-950">
      <header className="sticky top-0 z-20 flex h-16 items-center justify-between bg-white/95 px-7 backdrop-blur">
        <Link to="/" className="flex items-center gap-3">
          <img src={logo} alt="FastRead" className="h-9 w-9 rounded-md" />
          <span className="text-2xl font-semibold tracking-normal">FastRead</span>
        </Link>
        <div className="flex items-center gap-3">
          <Link
            to="/search"
            className="inline-flex h-10 items-center gap-2 rounded-full border border-neutral-200 px-4 text-sm font-medium text-neutral-900 transition hover:bg-neutral-50"
          >
            <Search className="h-4 w-4" />
            论文检索
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
                placeholder="搜索核验任务"
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
            <button
              type="button"
              className="inline-flex h-12 items-center gap-2 rounded-full border border-neutral-200 px-5 text-sm hover:bg-neutral-50"
            >
              最近
              <ChevronDown className="h-4 w-4" />
            </button>
          </div>
        </section>

        <section>
          <h2 className="mb-5 text-3xl font-medium tracking-normal">
            {query.trim() ? '搜索结果' : '最近核验任务'}
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
                />
              ))}
            </div>
          )}

          {visibleTasks.length === 0 && (
            <div className="mt-6 rounded-lg border border-dashed border-neutral-300 py-16 text-center">
              <SearchCheck className="mx-auto h-10 w-10 text-neutral-300" />
              <p className="mt-4 text-base font-medium text-neutral-800">还没有匹配的核验任务</p>
              <p className="mt-2 text-sm text-neutral-500">发起一次联网核实，报告和证据源会出现在这里。</p>
            </div>
          )}
        </section>
      </main>

      <Dialog open={Boolean(taskToDelete)} onOpenChange={open => !open && setTaskToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除这条核验任务？</DialogTitle>
            <DialogDescription>
              将删除「{taskToDelete ? getNotebookTitle(taskToDelete) : ''}」以及对应的本地核验报告和证据索引，此操作不可撤销。
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
    </div>
  )
}
