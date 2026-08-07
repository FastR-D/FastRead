import { useTaskStore } from '@/store/taskStore'
import { Badge } from '@/components/ui/badge.tsx'
import { cn } from '@/lib/utils.ts'
import { Folder, StickyNote, Tags, Trash } from 'lucide-react'
import { Button } from '@/components/ui/button.tsx'
import PinyinMatch from 'pinyin-match'
import Fuse from 'fuse.js'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip.tsx'
import LazyImage from '@/components/LazyImage.tsx'
import { FC, useMemo, useState } from 'react'

interface NoteHistoryProps {
  onSelect: (taskId: string) => void
  selectedId: string | null
}

const DEFAULT_FOLDER = '默认收藏夹'

const NoteHistory: FC<NoteHistoryProps> = ({ onSelect, selectedId }) => {
  const tasks = useTaskStore(state => state.tasks)
  const removeTask = useTaskStore(state => state.removeTask)
  const updateTaskCollection = useTaskStore(state => state.updateTaskCollection)
  const baseURL = (String(import.meta.env.VITE_API_BASE_URL || 'api')).replace(/\/$/, '')
  const [search, setSearch] = useState('')
  const [folderFilter, setFolderFilter] = useState('all')

  const folders = useMemo(() => {
    const uniqueFolders = new Set(
      tasks.map(task => task.collection?.folder || DEFAULT_FOLDER).filter(Boolean)
    )
    return [DEFAULT_FOLDER, ...Array.from(uniqueFolders).filter(folder => folder !== DEFAULT_FOLDER)]
  }, [tasks])

  const fuse = useMemo(
    () =>
      new Fuse(tasks, {
        keys: ['audioMeta.title', 'collection.folder', 'collection.tags', 'collection.note'],
        threshold: 0.35,
      }),
    [tasks]
  )

  const filteredTasks = useMemo(() => {
    const query = search.trim()
    const searchedTasks = query
      ? Array.from(
          new Map(
            [
              ...fuse.search(query).map(result => result.item),
              ...tasks.filter(task => PinyinMatch.match(task.audioMeta.title || '', query)),
            ].map(task => [task.id, task])
          ).values()
        )
      : tasks

    return searchedTasks.filter(task => {
      if (folderFilter === 'all') return true
      return (task.collection?.folder || DEFAULT_FOLDER) === folderFilter
    })
  }, [folderFilter, fuse, search, tasks])

  const selectedTask = tasks.find(task => task.id === selectedId) || null

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="space-y-2">
        <input
          type="text"
          placeholder="搜索标题、标签或备注"
          className="w-full rounded border border-neutral-300 px-3 py-1.5 text-sm outline-none focus:border-primary"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select
          className="w-full rounded border border-neutral-300 bg-white px-3 py-1.5 text-sm outline-none focus:border-primary"
          value={folderFilter}
          onChange={e => setFolderFilter(e.target.value)}
        >
          <option value="all">全部收藏夹</option>
          {folders.map(folder => (
            <option key={folder} value={folder}>
              {folder}
            </option>
          ))}
        </select>
      </div>

      {selectedTask && (
        <div className="space-y-2 rounded-md border border-neutral-200 bg-neutral-50 p-3">
          <div className="text-xs font-medium text-neutral-600">收藏信息</div>
          <input
            type="text"
            className="w-full rounded border border-neutral-200 bg-white px-2 py-1 text-xs outline-none focus:border-primary"
            value={selectedTask.collection?.folder || DEFAULT_FOLDER}
            onChange={e => updateTaskCollection(selectedTask.id, { folder: e.target.value })}
            placeholder="收藏夹"
          />
          <input
            type="text"
            className="w-full rounded border border-neutral-200 bg-white px-2 py-1 text-xs outline-none focus:border-primary"
            value={(selectedTask.collection?.tags || []).join('，')}
            onChange={e =>
              updateTaskCollection(selectedTask.id, {
                tags: e.target.value
                  .split(/[，,\s]+/)
                  .map(tag => tag.trim())
                  .filter(Boolean),
              })
            }
            placeholder="标签，用逗号分隔"
          />
          <textarea
            className="min-h-14 w-full resize-none rounded border border-neutral-200 bg-white px-2 py-1 text-xs outline-none focus:border-primary"
            value={selectedTask.collection?.note || ''}
            onChange={e => updateTaskCollection(selectedTask.id, { note: e.target.value })}
            placeholder="收藏备注"
          />
        </div>
      )}

      {filteredTasks.length === 0 ? (
        <div className="rounded-md border border-neutral-200 bg-neutral-50 py-6 text-center">
          <p className="text-sm text-neutral-500">暂无收藏视频</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2 overflow-hidden">
          {filteredTasks.map(task => {
            const folder = task.collection?.folder || DEFAULT_FOLDER
            const tags = task.collection?.tags || []
            return (
              <div
                key={task.id}
                onClick={() => onSelect(task.id)}
                className={cn(
                  'flex cursor-pointer flex-col rounded-md border border-neutral-200 p-3 transition-colors hover:bg-neutral-50',
                  selectedId === task.id && 'border-primary bg-primary-light'
                )}
              >
                <div className="flex items-center gap-3">
                  <LazyImage
                    src={
                      task.audioMeta.cover_url
                        ? `${baseURL}/image_proxy?url=${encodeURIComponent(task.audioMeta.cover_url)}`
                        : '/placeholder.png'
                    }
                    alt="封面"
                  />

                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div className="line-clamp-2 min-w-0 flex-1 text-sm">
                          {task.audioMeta.title || '未命名知识卡片'}
                        </div>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>{task.audioMeta.title || '未命名知识卡片'}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
                  <Badge variant="secondary" className="gap-1 rounded-sm px-1.5 py-0">
                    <Folder className="h-3 w-3" />
                    {folder}
                  </Badge>
                  {tags.slice(0, 2).map(tag => (
                    <Badge key={tag} variant="outline" className="gap-1 rounded-sm px-1.5 py-0">
                      <Tags className="h-3 w-3" />
                      {tag}
                    </Badge>
                  ))}
                  {task.collection?.note && (
                    <Badge variant="outline" className="gap-1 rounded-sm px-1.5 py-0">
                      <StickyNote className="h-3 w-3" />
                      备注
                    </Badge>
                  )}
                </div>

                <div className="mt-2 flex items-center justify-between text-[10px]">
                  <div className="shrink-0">
                    {task.status === 'SUCCESS' && (
                      <div className="w-12 rounded bg-primary p-0.5 text-center text-white">
                        已完成
                      </div>
                    )}
                    {task.status !== 'SUCCESS' && task.status !== 'FAILED' && (
                      <div className="w-12 rounded bg-green-500 p-0.5 text-center text-white">
                        生成中
                      </div>
                    )}
                    {task.status === 'FAILED' && (
                      <div className="w-12 rounded bg-red-500 p-0.5 text-center text-white">
                        失败
                      </div>
                    )}
                  </div>

                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={e => {
                            e.stopPropagation()
                            removeTask(task.id)
                          }}
                          className="shrink-0"
                        >
                          <Trash className="h-4 w-4 text-muted-foreground" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>删除</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default NoteHistory
