import { useState, useEffect, memo, FC, useCallback } from 'react'
import { toast } from 'react-hot-toast'
import WorkspaceStatusView from '@/pages/HomePage/components/WorkspaceStatusView.tsx'
import TaskFailureView from '@/pages/HomePage/components/TaskFailureView.tsx'
import { useTaskStore } from '@/store/taskStore'
import { noteStyles } from '@/constant/note.ts'
import { MarkdownHeader } from '@/pages/HomePage/components/MarkdownHeader.tsx'
import WorkspacePanels from '@/pages/HomePage/components/WorkspacePanels.tsx'

interface VersionNote {
  ver_id: string
  content: string
  style: string
  model_name: string
  created_at?: string
}

interface MarkdownViewerProps {
  content?: string | VersionNote[]
  status: 'idle' | 'loading' | 'success' | 'failed'
}

type WorkspaceCommand = {
  viewMode?: 'report' | 'verify' | 'map' | 'preview' | 'cards'
  chat?: false | 'half' | 'full'
  transcribe?: boolean | 'toggle'
  action?: 'copy' | 'download'
}

const steps = [
  { label: '解析输入', key: 'EXTRACTING_CLAIMS' },
  { label: '提取主张', key: 'SEARCHING_WEB' },
  { label: '联网检索', key: 'FETCHING_SOURCES' },
  { label: '抓取证据', key: 'EVALUATING_EVIDENCE' },
  { label: '生成报告', key: 'WRITING_REPORT' },
  { label: '核实完成', key: 'SUCCESS' },
]

const MarkdownViewer: FC<MarkdownViewerProps> = memo(({ status }) => {
  const [currentVerId, setCurrentVerId] = useState<string>('')
  const [selectedContent, setSelectedContent] = useState<string>('')
  const [modelName, setModelName] = useState<string>('')
  const [style, setStyle] = useState<string>('')
  const [createTime, setCreateTime] = useState<string>('')
  const currentTask = useTaskStore(state => state.getCurrentTask())
  const taskStatus = currentTask?.status || 'PENDING'
  const retryTask = useTaskStore.getState().retryTask
  const isMultiVersion = Array.isArray(currentTask?.markdown)
  const [showTranscribe, setShowTranscribe] = useState(false)
  const [showChat, setShowChat] = useState<false | 'half' | 'full'>(false)
  const [viewMode, setViewMode] = useState<'report' | 'verify' | 'map' | 'preview' | 'cards'>('report')
  const hasVerificationReport = Boolean(currentTask?.insights?.verification)

  // 多版本内容处理
  useEffect(() => {
    if (!currentTask) return

    if (!isMultiVersion) {
      setCurrentVerId('') // 清空旧版本 ID
      setModelName(currentTask.formData.model_name)
      setStyle(currentTask.formData.style)
      setCreateTime(currentTask.createdAt)
      setSelectedContent(currentTask?.markdown)
    } else {
      const latestVersion = [...currentTask.markdown].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )[0]

      if (latestVersion) {
        setCurrentVerId(latestVersion.ver_id)
      }
    }
  }, [currentTask, isMultiVersion, taskStatus])
  useEffect(() => {
    if (!currentTask || !isMultiVersion) return

    const currentVer = currentTask.markdown.find(v => v.ver_id === currentVerId)
    if (currentVer) {
      setModelName(currentVer.model_name)
      setStyle(currentVer.style)
      setCreateTime(currentVer.created_at || '')
      setSelectedContent(currentVer.content)
    }
  }, [currentTask, currentVerId, isMultiVersion])
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(selectedContent)
      toast.success('已复制到剪贴板')
    } catch {
      toast.error('复制失败')
    }
  }, [selectedContent])
  const handleDownload = useCallback(() => {
    const name = currentTask?.audioMeta.title || 'note'
    const blob = new Blob([selectedContent], { type: 'text/markdown;charset=utf-8' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${name}.md`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }, [currentTask?.audioMeta.title, selectedContent])

  useEffect(() => {
    const handleWorkspaceCommand = (event: Event) => {
      const command = (event as CustomEvent<WorkspaceCommand>).detail
      if (!command) return

      if (command.viewMode) {
        setViewMode(command.viewMode)
      }
      if (command.chat !== undefined) {
        if (!command.viewMode && command.chat === 'full') setViewMode('report')
        setShowChat(command.chat)
      }
      if (command.transcribe !== undefined) {
        setViewMode('preview')
        setShowTranscribe(prev =>
          command.transcribe === 'toggle' ? !prev : Boolean(command.transcribe)
        )
      }
      if (command.action === 'copy') {
        handleCopy()
      }
      if (command.action === 'download') {
        handleDownload()
      }
    }

    window.addEventListener('reelmind:workspace-command', handleWorkspaceCommand)
    return () => {
      window.removeEventListener('reelmind:workspace-command', handleWorkspaceCommand)
    }
  }, [handleCopy, handleDownload])

  if (status === 'loading' && !hasVerificationReport) {
    return (
      <div className="flex h-screen w-full">
        <WorkspaceStatusView mode="loading" steps={steps} currentStep={taskStatus} />
      </div>
    )
  }

  if (status === 'idle') {
    return <WorkspaceStatusView mode="idle" />
  }

  if (status === 'failed' && !isMultiVersion && !hasVerificationReport) {
    const failure = currentTask?.error
    return (
      <TaskFailureView
        title={failure?.title || '联网核实失败'}
        message={failure?.message || currentTask?.message || '请检查后台或稍后再试'}
        retryHint={failure?.retry_hint}
        rawMessage={failure?.raw_message}
        canRetry={!!currentTask}
        onRetry={() => currentTask && retryTask(currentTask.id)}
      />
    )
  }

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden">
      <MarkdownHeader
        currentTask={currentTask}
        isMultiVersion={isMultiVersion}
        currentVerId={currentVerId}
        setCurrentVerId={setCurrentVerId}
        modelName={modelName}
        style={style}
        noteStyles={noteStyles}
        onCopy={handleCopy}
        onDownload={handleDownload}
        createAt={createTime}
        showTranscribe={showTranscribe}
        setShowTranscribe={setShowTranscribe}
        showChat={showChat}
        setShowChat={setShowChat}
        viewMode={viewMode}
        setViewMode={setViewMode}
      />

      <WorkspacePanels
        viewMode={viewMode}
        showChat={showChat}
        showTranscribe={showTranscribe}
        selectedContent={selectedContent}
        currentTask={currentTask}
        setShowChat={setShowChat}
      />
    </div>
  )
})

MarkdownViewer.displayName = 'MarkdownViewer'

export default MarkdownViewer
