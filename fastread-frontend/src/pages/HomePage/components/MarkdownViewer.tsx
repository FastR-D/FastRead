import { memo, type FC, useEffect, useState } from 'react'
import TaskFailureView from '@/pages/HomePage/components/TaskFailureView'
import WorkspacePanels, { type ReadingViewMode } from '@/pages/HomePage/components/WorkspacePanels'
import WorkspaceStatusView from '@/pages/HomePage/components/WorkspaceStatusView'
import { useTaskStore } from '@/store/taskStore'

interface MarkdownViewerProps {
  status: 'idle' | 'loading' | 'success' | 'failed'
}

type WorkspaceCommand = {
  viewMode?: ReadingViewMode
  chat?: false | 'half' | 'full'
}

const paperSteps = [
  { label: '解析 PDF / URL', key: 'PARSING' },
  { label: '保留分页原文', key: 'DOWNLOADING' },
  { label: '准备阅读报告', key: 'SUCCESS' },
]

const auditSteps = [
  { label: '提取主张', key: 'EXTRACTING_CLAIMS' },
  { label: '联网检索', key: 'SEARCHING_WEB' },
  { label: '抓取证据', key: 'FETCHING_SOURCES' },
  { label: '评估证据', key: 'EVALUATING_EVIDENCE' },
  { label: '写入审计', key: 'WRITING_REPORT' },
  { label: '审计完成', key: 'SUCCESS' },
]

const MarkdownViewer: FC<MarkdownViewerProps> = memo(({ status }) => {
  const currentTask = useTaskStore(state => state.getCurrentTask())
  const retryTask = useTaskStore.getState().retryTask
  const isPaper = currentTask?.platform === 'paper' || Boolean(currentTask?.paperDocument)
  const hasVerification = Boolean(currentTask?.insights?.verification)
  const [viewMode, setViewMode] = useState<ReadingViewMode>('source')

  useEffect(() => {
    if (!currentTask) {
      setViewMode('source')
      return
    }
    setViewMode(isPaper ? 'source' : hasVerification ? 'evidence' : 'report')
  }, [currentTask?.id, hasVerification, isPaper])

  useEffect(() => {
    const handleWorkspaceCommand = (event: Event) => {
      const command = (event as CustomEvent<WorkspaceCommand>).detail
      if (!command) return
      if (command.viewMode) setViewMode(command.viewMode)
      if (command.chat) setViewMode('chat')
    }
    window.addEventListener('fastread:workspace-command', handleWorkspaceCommand)
    return () => window.removeEventListener('fastread:workspace-command', handleWorkspaceCommand)
  }, [])

  if (status === 'loading' && !hasVerification && !currentTask?.paperDocument) {
    return (
      <div className="flex h-full w-full">
        <WorkspaceStatusView
          mode="loading"
          steps={isPaper ? paperSteps : auditSteps}
          currentStep={currentTask?.status || 'PENDING'}
        />
      </div>
    )
  }

  if (status === 'idle') return <WorkspaceStatusView mode="idle" />

  if (status === 'failed' && !hasVerification && !currentTask?.paperDocument) {
    const failure = currentTask?.error
    return (
      <TaskFailureView
        title={failure?.title || (isPaper ? '论文导入失败' : '证据审计失败')}
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
        setViewMode={setViewMode}
      />
    </div>
  )
})

MarkdownViewer.displayName = 'MarkdownViewer'

export default MarkdownViewer
