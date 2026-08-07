import NoteHistory from '@/pages/HomePage/components/NoteHistory.tsx'
import { useTaskStore } from '@/store/taskStore'
import { Bookmark } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
const History = () => {
  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-3 px-2.5 py-1.5">
        <div className="flex h-10 shrink-0 items-center gap-2">
          <Bookmark className="h-4 w-4 text-neutral-500" />
          <h2 className="text-base font-medium text-neutral-900">我的收藏</h2>
        </div>
        <ScrollArea className="min-h-0 w-full flex-1">
          <NoteHistory onSelect={setCurrentTask} selectedId={currentTaskId} />
        </ScrollArea>
      </div>
  )
}

export default History
