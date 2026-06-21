import { FC } from 'react'
import { AlertTriangle, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button.tsx'

interface TaskFailureViewProps {
  title?: string
  message?: string
  retryHint?: string
  rawMessage?: string
  canRetry?: boolean
  onRetry?: () => void
}

const TaskFailureView: FC<TaskFailureViewProps> = ({
  title = '联网核实失败',
  message = '请检查后台或稍后再试',
  retryHint,
  rawMessage,
  canRetry = true,
  onRetry,
}) => {
  return (
    <div className="flex min-h-full w-full items-center justify-center bg-slate-50/40 px-6">
      <div className="w-full max-w-md">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-red-200 bg-red-50 text-red-500">
            <AlertTriangle className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-base font-semibold text-red-600">{title}</p>
            <p className="mt-1.5 text-sm leading-6 text-neutral-700">{message}</p>
            {retryHint && (
              <p className="mt-2 text-xs leading-5 text-neutral-500">{retryHint}</p>
            )}
          </div>
        </div>

        {rawMessage && (
          <details className="mt-4 ml-12 text-xs text-neutral-500">
            <summary className="cursor-pointer select-none text-neutral-500 hover:text-neutral-700">
              错误详情
            </summary>
            <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap rounded-md border border-neutral-200 bg-neutral-50 p-2 font-mono text-[11px] leading-5 text-neutral-600">
              {rawMessage}
            </pre>
          </details>
        )}

        <div className="mt-5 ml-12 flex">
          <Button
            onClick={onRetry}
            size="sm"
            variant="default"
            disabled={!canRetry}
            className="gap-1.5"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            重试
          </Button>
        </div>
      </div>
    </div>
  )
}

export default TaskFailureView
