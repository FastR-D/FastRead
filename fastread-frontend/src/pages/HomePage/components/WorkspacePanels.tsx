import { lazy, Suspense, type FC, type ReactNode } from 'react'
import type { Task } from '@/store/taskStore'

const ChatPanel = lazy(() => import('@/pages/HomePage/components/ChatPanel'))
const PaperSourceView = lazy(() => import('@/pages/HomePage/components/PaperSourceView'))
const PersonalSummaryView = lazy(() => import('@/pages/HomePage/components/PersonalSummaryView'))
const ReadingReportView = lazy(() => import('@/pages/HomePage/components/ReadingReportView'))
const RelatedWorkView = lazy(() => import('@/pages/HomePage/components/RelatedWorkView'))

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
  let panel: ReactNode
  if (viewMode === 'source') {
    panel = (
      <PaperSourceView
        task={currentTask}
        page={sourcePage}
        quote={sourceQuote}
        onLocationChange={onSourceLocationChange}
      />
    )
  }
  else if (viewMode === 'report') {
    panel = <ReadingReportView task={currentTask} />
  }
  else if (viewMode === 'summary') {
    panel = <PersonalSummaryView task={currentTask} />
  }
  else if (viewMode === 'related') {
    panel = <RelatedWorkView task={currentTask} />
  }
  else if (viewMode === 'chat') {
    panel = currentTask ? (
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
  else {
    panel = <PaperSourceView task={currentTask} page={sourcePage} quote={sourceQuote} onLocationChange={onSourceLocationChange} />
  }
  return (
    <Suspense fallback={<div className="flex h-full items-center justify-center text-sm text-slate-500">面板加载中…</div>}>
      {panel}
    </Suspense>
  )
}

export default WorkspacePanels
