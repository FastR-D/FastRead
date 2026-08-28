import { FC } from 'react'
import type { Task } from '@/store/taskStore'
import ChatPanel from '@/pages/HomePage/components/ChatPanel'
import PaperSourceView from '@/pages/HomePage/components/PaperSourceView'
import PersonalSummaryView from '@/pages/HomePage/components/PersonalSummaryView'
import ReadingReportView from '@/pages/HomePage/components/ReadingReportView'
import RelatedWorkView from '@/pages/HomePage/components/RelatedWorkView'

export type ReadingViewMode = 'source' | 'report' | 'related' | 'summary' | 'chat'

interface WorkspacePanelsProps {
  viewMode: ReadingViewMode
  currentTask: Task | null
  setViewMode: (mode: ReadingViewMode) => void
  sourcePage?: number
  sourceQuote?: string
  onSourceLocationChange: (page: number, quote?: string) => void
}

const WorkspacePanels: FC<WorkspacePanelsProps> = ({
  viewMode,
  currentTask,
  setViewMode,
  sourcePage,
  sourceQuote,
  onSourceLocationChange,
}) => {
  if (viewMode === 'source') {
    return (
      <PaperSourceView
        task={currentTask}
        page={sourcePage}
        quote={sourceQuote}
        onLocationChange={onSourceLocationChange}
      />
    )
  }
  if (viewMode === 'report') {
    return <ReadingReportView task={currentTask} />
  }
  if (viewMode === 'summary') {
    return <PersonalSummaryView task={currentTask} />
  }
  if (viewMode === 'related') {
    return <RelatedWorkView task={currentTask} />
  }
  if (viewMode === 'chat') {
    return currentTask ? (
      <ChatPanel
        taskId={currentTask.id}
        mode="full"
        onModeChange={mode => {
          if (!mode) setViewMode('report')
        }}
      />
    ) : (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">请先导入论文。</div>
    )
  }
  return <PaperSourceView task={currentTask} page={sourcePage} quote={sourceQuote} onLocationChange={onSourceLocationChange} />
}

export default WorkspacePanels
