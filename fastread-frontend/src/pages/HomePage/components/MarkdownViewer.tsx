import { memo, type FC, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import TaskFailureView from '@/pages/HomePage/components/TaskFailureView'
import WorkspacePanels, { type ReadingViewMode } from '@/pages/HomePage/components/WorkspacePanels'
import WorkspaceStatusView from '@/pages/HomePage/components/WorkspaceStatusView'
import { useTaskStore } from '@/store/taskStore'
import {
  buildWorkspaceSearch,
  parseWorkspaceLocation,
  type WorkspaceCommandDetail,
} from '@/utils/workspaceNavigation'

interface MarkdownViewerProps {
  status: 'idle' | 'loading' | 'success' | 'failed'
}

const paperSteps = [
  { label: '解析 PDF / URL', key: 'PARSING_DOCUMENT' },
  { label: '准备阅读报告', key: 'SUCCESS' },
]

const MarkdownViewer: FC<MarkdownViewerProps> = memo(({ status }) => {
  const currentTask = useTaskStore(state => state.getCurrentTask())
  const currentTaskId = currentTask?.id
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const recordReadingProgress = useTaskStore(state => state.recordReadingProgress)
  const retryTask = useTaskStore.getState().retryTask
  const [viewMode, setViewMode] = useState<ReadingViewMode>('source')
  const [searchParams, setSearchParams] = useSearchParams()
  const workspaceLocation = parseWorkspaceLocation(searchParams)
  const firstPaperPage = currentTask?.paperDocument?.pages?.[0]?.page

  useEffect(() => {
    if (!currentTaskId) {
      setViewMode('source')
      return
    }
    if (!workspaceLocation.taskId || workspaceLocation.taskId === currentTaskId) {
      setViewMode(workspaceLocation.view)
      return
    }
    setViewMode('source')
  }, [currentTaskId, workspaceLocation.taskId, workspaceLocation.view])

  useEffect(() => {
    if (!currentTaskId) return
    recordReadingProgress(currentTaskId, {
      view: viewMode,
      page: viewMode === 'source' ? workspaceLocation.page || firstPaperPage || 1 : undefined,
    })
  }, [currentTaskId, firstPaperPage, recordReadingProgress, viewMode, workspaceLocation.page])

  useEffect(() => {
    const handleWorkspaceCommand = (event: Event) => {
      const command = (event as CustomEvent<WorkspaceCommandDetail>).detail
      if (!command) return
      const nextView = command.chat ? 'chat' : command.viewMode || viewMode
      const nextTaskId = command.taskId || currentTask?.id
      if (command.taskId) setCurrentTask(command.taskId)
      setViewMode(nextView)
      setSearchParams(buildWorkspaceSearch({
        taskId: nextTaskId,
        view: nextView,
        page: nextView === 'source' ? command.page : undefined,
        quote: nextView === 'source' ? command.quote : undefined,
      }), { replace: true })
    }
    window.addEventListener('fastread:workspace-command', handleWorkspaceCommand)
    return () => window.removeEventListener('fastread:workspace-command', handleWorkspaceCommand)
  }, [currentTask?.id, setCurrentTask, setSearchParams, viewMode])

  const navigateToView = (nextView: ReadingViewMode) => {
    setViewMode(nextView)
    setSearchParams(buildWorkspaceSearch({ taskId: currentTask?.id, view: nextView }), { replace: true })
  }

  const updateSourceLocation = (page: number, quote?: string) => {
    setSearchParams(buildWorkspaceSearch({
      taskId: currentTask?.id,
      view: 'source',
      page,
      quote,
    }), { replace: true })
  }

  if (status === 'loading' && !currentTask?.paperDocument) {
    return (
      <div className="flex h-full w-full">
        <WorkspaceStatusView
          mode="loading"
          steps={paperSteps}
          currentStep={currentTask?.status || 'PENDING'}
        />
      </div>
    )
  }

  if (status === 'idle') return <WorkspaceStatusView mode="idle" />

  if (status === 'failed' && !currentTask?.paperDocument) {
    const failure = currentTask?.error
    return (
      <TaskFailureView
        title={failure?.title || '论文导入失败'}
        message={failure?.message || currentTask?.message || '请检查后台或稍后再试'}
        retryHint={failure?.retry_hint}
        rawMessage={failure?.raw_message}
        canRetry={Boolean(currentTask)}
        onRetry={() => currentTask && retryTask(currentTask.id)}
      />
    )
  }

  return (
    <div className="h-full min-h-0 w-full overflow-hidden">
      <WorkspacePanels
        viewMode={viewMode}
        currentTask={currentTask}
        setViewMode={navigateToView}
        sourcePage={workspaceLocation.page}
        sourceQuote={workspaceLocation.quote}
        onSourceLocationChange={updateSourceLocation}
      />
    </div>
  )
})

MarkdownViewer.displayName = 'MarkdownViewer'

export default MarkdownViewer
