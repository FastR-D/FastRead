import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  BookOpen,
  Check,
  ChevronDown,
  Grid2X2,
  List,
  Loader2,
  MoreVertical,
  Plus,
  Search,
  Settings,
  Tags,
} from 'lucide-react'
import logo from '@/assets/icon.svg'
import { useTaskStore, type Task } from '@/store/taskStore'
import { cn } from '@/lib/utils'

type LibraryFilter = 'all' | 'mine' | 'featured'
type ViewMode = 'grid' | 'list'

const apiBase = () => String(import.meta.env.VITE_API_BASE_URL || 'api').replace(/\/$/, '')

function coverUrl(task: Task) {
  const rawCover = task.audioMeta?.cover_url
  if (!rawCover) return ''
  return `${apiBase()}/image_proxy?url=${encodeURIComponent(rawCover)}`
}

function getNotebookTitle(task: Task) {
  return task.audioMeta?.title || task.collection?.note || '未命名视频笔记'
}

function getSourceCount(task: Task) {
  const transcriptCount = task.transcript?.segments?.length || 0
  const cardCount = task.insights?.cards?.length || 0
  if (transcriptCount > 0) return transcriptCount
  if (cardCount > 0) return cardCount
  return task.status === 'SUCCESS' ? 1 : 0
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
  if (task.status === 'FAILED') return '生成失败'
  return '生成中'
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
    'bg-[#ece8f0] text-[#17151d]',
    'bg-[#eef0fb] text-[#171b2d]',
    'bg-[#dff2f5] text-[#10262d]',
    'bg-[#f4ece7] text-[#241915]',
    'bg-[#f0f3e8] text-[#1f2619]',
    'bg-[#f2eaf3] text-[#231724]',
  ]
  const icons = ['▱', '⌁', '●', '◩', '⌬', '□']
  return (
    <div className={cn('absolute inset-0', palettes[index % palettes.length])}>
      <div className="absolute left-8 top-7 text-4xl opacity-80">{icons[index % icons.length]}</div>
      <div className="absolute bottom-6 right-7 h-24 w-24 rounded-full border border-black/10" />
      <div className="absolute right-24 top-10 h-8 w-20 rounded-full border border-black/10" />
      <div className="absolute bottom-12 left-10 h-2 w-32 rounded-full bg-black/10" />
    </div>
  )
}

function FeaturedNotebookCard({
  task,
  index,
  onOpen,
}: {
  task: Task
  index: number
  onOpen: (taskId: string) => void
}) {
  const image = coverUrl(task)

  return (
    <button
      type="button"
      onClick={() => onOpen(task.id)}
      className="group relative h-[168px] overflow-hidden rounded-lg text-left shadow-sm outline-none transition hover:-translate-y-0.5 hover:shadow-md focus-visible:ring-2 focus-visible:ring-primary"
    >
      {image ? (
        <img
          src={image}
          alt=""
          referrerPolicy="no-referrer"
          className="absolute inset-0 h-full w-full object-cover transition duration-300 group-hover:scale-[1.03]"
        />
      ) : (
        <FlatPattern index={index} />
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/25 to-black/10" />
      <div className="relative flex h-full flex-col justify-end p-5 text-white">
        <div className="mb-3 flex items-center gap-2 text-sm text-white/85">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/90 text-primary">
            <BookOpen className="h-4 w-4" />
          </span>
          <span className="truncate">{task.collection?.folder || '默认收藏夹'}</span>
        </div>
        <h3 className="line-clamp-2 text-xl font-medium leading-snug">{getNotebookTitle(task)}</h3>
        <div className="mt-3 flex items-center justify-between gap-3 text-sm text-white/85">
          <span className="truncate">
            {formatDate(task.createdAt)} · {getSourceCount(task)} 个来源
          </span>
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white/20">
            <BookOpen className="h-4 w-4" />
          </span>
        </div>
      </div>
    </button>
  )
}

function RecentNotebookCard({
  task,
  index,
  viewMode,
  onOpen,
}: {
  task: Task
  index: number
  viewMode: ViewMode
  onOpen: (taskId: string) => void
}) {
  const image = coverUrl(task)
  const tags = task.collection?.tags || []

  if (viewMode === 'list') {
    return (
      <button
        type="button"
        onClick={() => onOpen(task.id)}
        className="flex min-h-24 w-full items-center gap-4 rounded-lg border border-neutral-200 bg-white px-4 py-3 text-left transition hover:border-neutral-300 hover:bg-neutral-50 focus-visible:ring-2 focus-visible:ring-primary"
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
        <StatusMark task={task} />
      </button>
    )
  }

  return (
    <button
      type="button"
      onClick={() => onOpen(task.id)}
      className="group relative h-[168px] overflow-hidden rounded-lg border border-transparent text-left outline-none transition hover:-translate-y-0.5 hover:shadow-md focus-visible:ring-2 focus-visible:ring-primary"
    >
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
      <div className={cn('relative flex h-full flex-col p-5', image ? 'text-white' : 'text-neutral-950')}>
        <div className="flex items-start justify-between gap-3">
          <div className="text-3xl leading-none">{['🧘', '📉', '🧠', '🎓', '🤖', '📚'][index % 6]}</div>
          <MoreVertical className={cn('h-4 w-4', image ? 'text-white/80' : 'text-neutral-500')} />
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
    </button>
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
      <span className="mt-4 text-lg font-medium">新建笔记本</span>
    </button>
  )
}

export default function LibraryPage() {
  const navigate = useNavigate()
  const tasks = useTaskStore(state => state.tasks)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<LibraryFilter>('all')
  const [viewMode, setViewMode] = useState<ViewMode>('grid')

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
    if (filter === 'featured') {
      return searchedTasks.filter(task => task.status === 'SUCCESS' && task.insights?.cards?.length)
    }
    return searchedTasks
  }, [filter, searchedTasks])

  const featuredTasks = useMemo(
    () => sortedTasks.filter(task => task.status === 'SUCCESS').slice(0, 4),
    [sortedTasks]
  )

  const openTask = (taskId: string) => {
    setCurrentTask(taskId)
    navigate('/workspace')
  }

  const createTask = () => {
    setCurrentTask(null)
    navigate('/workspace')
  }

  const tabs: Array<{ id: LibraryFilter; label: string }> = [
    { id: 'all', label: '全部' },
    { id: 'mine', label: '我的笔记本' },
    { id: 'featured', label: '精选笔记本' },
  ]

  return (
    <div className="h-screen overflow-y-auto bg-white text-neutral-950">
      <header className="sticky top-0 z-20 flex h-16 items-center justify-between bg-white/95 px-7 backdrop-blur">
        <Link to="/" className="flex items-center gap-3">
          <img src={logo} alt="ReelMind" className="h-9 w-9 rounded-md" />
          <span className="text-2xl font-semibold tracking-normal">ReelMind</span>
        </Link>
        <div className="flex items-center gap-3">
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
            新建
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
                placeholder="搜索笔记本"
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

        {featuredTasks.length > 0 && filter !== 'featured' && !query.trim() && (
          <section>
            <div className="mb-5 flex items-end justify-between">
              <h1 className="text-3xl font-medium tracking-normal">精选笔记本</h1>
              <button
                type="button"
                onClick={() => setFilter('featured')}
                className="rounded-full border border-neutral-200 px-5 py-2 text-sm font-medium hover:bg-neutral-50"
              >
                查看全部
              </button>
            </div>
            <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
              {featuredTasks.map((task, index) => (
                <FeaturedNotebookCard key={task.id} task={task} index={index} onOpen={openTask} />
              ))}
            </div>
          </section>
        )}

        <section>
          <h2 className="mb-5 text-3xl font-medium tracking-normal">
            {query.trim() ? '搜索结果' : '最近打开过的笔记本'}
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
                />
              ))}
            </div>
          )}

          {visibleTasks.length === 0 && (
            <div className="mt-6 rounded-lg border border-dashed border-neutral-300 py-16 text-center">
              <BookOpen className="mx-auto h-10 w-10 text-neutral-300" />
              <p className="mt-4 text-base font-medium text-neutral-800">还没有匹配的笔记本</p>
              <p className="mt-2 text-sm text-neutral-500">新建一个视频笔记，生成后会出现在这里。</p>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
