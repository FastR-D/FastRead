import { FC } from 'react'
import { Task } from '@/store/taskStore'
import WorkspaceStatusView from '@/pages/HomePage/components/WorkspaceStatusView.tsx'
import ChatPanel from '@/pages/HomePage/components/ChatPanel.tsx'
import MarkdownDocument from '@/pages/HomePage/components/MarkdownDocument.tsx'
import VerificationReportView from '@/pages/HomePage/components/VerificationReportView.tsx'
import ReadingReportView from '@/pages/HomePage/components/ReadingReportView.tsx'

type ViewMode = 'report' | 'verify' | 'preview'
type ChatMode = false | 'half' | 'full'

interface WorkspacePanelsProps {
  viewMode: ViewMode
  showChat: ChatMode
  selectedContent: string
  currentTask: Task | null
  setShowChat: (mode: ChatMode) => void
}

const WorkspacePanels: FC<WorkspacePanelsProps> = ({
  viewMode,
  showChat,
  selectedContent,
  currentTask,
  setShowChat,
}) =>
  viewMode === 'report' ? (
    <div className="flex min-h-0 flex-1 overflow-hidden bg-slate-50/40">
      {showChat === 'full' && currentTask ? (
        <div className="h-full min-h-0 w-full overflow-hidden">
          <ChatPanel taskId={currentTask.id} mode="full" onModeChange={setShowChat} />
        </div>
      ) : (
        <>
          <div className="min-w-0 flex-1"><ReadingReportView task={currentTask} /></div>
          {showChat === 'half' && currentTask && (
            <div className="h-full min-h-0 w-1/2 shrink-0 overflow-hidden">
              <ChatPanel taskId={currentTask.id} mode="half" onModeChange={setShowChat} />
            </div>
          )}
        </>
      )}
    </div>
  ) : viewMode === 'verify' ? (
    <div className="flex min-h-0 flex-1 overflow-hidden bg-slate-50/40">
      {showChat === 'full' && currentTask ? (
        <div className="h-full min-h-0 w-full overflow-hidden">
          <ChatPanel taskId={currentTask.id} mode="full" onModeChange={setShowChat} />
        </div>
      ) : (
        <>
          <div className="min-w-0 flex-1"><VerificationReportView task={currentTask} /></div>
          {showChat === 'half' && currentTask && (
            <div className="h-full min-h-0 w-1/2 shrink-0 overflow-hidden">
              <ChatPanel taskId={currentTask.id} mode="half" onModeChange={setShowChat} />
            </div>
          )}
        </>
      )}
    </div>
  ) : (
    <div className="flex flex-1 overflow-hidden bg-white py-2">
      {selectedContent && selectedContent !== 'loading' && selectedContent !== 'empty' ? (
        <>
          {showChat === 'full' && currentTask ? (
            <div className="h-full min-h-0 w-full overflow-hidden">
              <ChatPanel taskId={currentTask.id} mode="full" onModeChange={setShowChat} />
            </div>
          ) : (
          <>
          <MarkdownDocument selectedContent={selectedContent} />
          {/* 侧边问答模式：markdown + ChatPanel 各占一半 */}
          {showChat === 'half' && currentTask && (
            <div className="ml-2 h-full min-h-0 w-1/2 shrink-0 overflow-hidden">
              <ChatPanel taskId={currentTask.id} mode="half" onModeChange={setShowChat} />
            </div>
          )}
          </>
          )}
        </>
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <WorkspaceStatusView mode="empty" />
        </div>
      )}
    </div>
  )

WorkspacePanels.displayName = 'WorkspacePanels'

export default WorkspacePanels
