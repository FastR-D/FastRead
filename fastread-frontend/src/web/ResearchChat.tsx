import { createContext, useContext, useEffect, type ReactNode } from 'react'
import {
  AssistantRuntimeProvider,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
  useExternalStoreRuntime,
  type ThreadMessageLike,
} from '@assistant-ui/react'

type Row = Record<string, any>
const RenderMessage = createContext<(message: Row) => ReactNode>(() => null)
function Message() {
  const row = useAuiState(s => s.message.metadata.custom.row) as Row
  const render = useContext(RenderMessage)
  return row ? <MessagePrimitive.Root>{render(row)}</MessagePrimitive.Root> : null
}
export function ResearchMessages() {
  return <ThreadPrimitive.Messages components={{ Message }} />
}
export default function ResearchChat({
  messages,
  running,
  disabled,
  question,
  onSend,
  renderMessage,
  children,
}: {
  messages: Row[]
  running: boolean
  disabled: boolean
  question: string
  onSend: (text: string) => Promise<boolean | undefined>
  renderMessage: (message: Row) => ReactNode
  children: ReactNode
}) {
  const runtime = useExternalStoreRuntime({
    messages,
    isRunning: running,
    isDisabled: disabled,
    convertMessage: (row: Row): ThreadMessageLike => ({
      id: row.id,
      role: row.role === 'user' ? 'user' : 'assistant',
      content: [{ type: 'text', text: row.content || '' }],
      metadata: { custom: { row } },
    }),
    onNew: async message => {
      const text = message.content
        .filter(p => p.type === 'text')
        .map(p => p.text)
        .join('\n')
      const sent = await onSend(text)
      if (!sent) runtime.thread.composer.setText(text)
    },
  })
  useEffect(() => {
    if (runtime.thread.composer.getState().text !== question)
      runtime.thread.composer.setText(question)
  }, [runtime, question])
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <RenderMessage.Provider value={renderMessage}>
        <ThreadPrimitive.Root className="desk-chat research-tool" data-assistant-ui="thread">
          {children}
        </ThreadPrimitive.Root>
      </RenderMessage.Provider>
    </AssistantRuntimeProvider>
  )
}
