import { FC } from 'react'
import { Task } from '@/store/taskStore'
import WorkspaceStatusView from '@/pages/HomePage/components/WorkspaceStatusView.tsx'
import TranscriptViewer from '@/pages/HomePage/components/transcriptViewer.tsx'
import MarkmapEditor from '@/pages/HomePage/components/MarkmapComponent.tsx'
import ChatPanel from '@/pages/HomePage/components/ChatPanel.tsx'
import KnowledgeCardsView from '@/pages/HomePage/components/KnowledgeCardsView.tsx'
import MarkdownDocument from '@/pages/HomePage/components/MarkdownDocument.tsx'
import VerificationReportView from '@/pages/HomePage/components/VerificationReportView.tsx'
import ReadingReportView from '@/pages/HomePage/components/ReadingReportView.tsx'

type ViewMode = 'report' | 'verify' | 'map' | 'preview' | 'cards'
type ChatMode = false | 'half' | 'full'

interface WorkspacePanelsProps {
  viewMode: ViewMode
  showChat: ChatMode
  showTranscribe: boolean
  selectedContent: string
  currentTask: Task | null
  setShowChat: (mode: ChatMode) => void
}

const WorkspacePanels: FC<WorkspacePanelsProps> = ({
  viewMode,
  showChat,
  showTranscribe,
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
  ) : viewMode === 'map' ? (
    <div className="flex min-h-0 w-full flex-1 overflow-hidden bg-white">
      <div className="min-h-0 w-full">
        <MarkmapEditor
          value={selectedContent}
          onChange={() => {}}
          height="100%" // 根据需求可以设定百分比或固定高度
          title={currentTask?.audioMeta?.title || '思维导图'}
        />
      </div>
    </div>
  ) : viewMode === 'cards' ? (
    <div className="flex flex-1 overflow-hidden bg-white">
      <KnowledgeCardsView taskId={currentTask?.id} insights={currentTask?.insights} />
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
          <MarkdownDocument
            selectedContent={selectedContent}
            audioMeta={currentTask?.audioMeta}
            videoUrl={currentTask?.formData?.video_url}
          />
          {showTranscribe && (
            <div className={'ml-2 w-2/4'}>
              <TranscriptViewer />
            </div>
          )}
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
