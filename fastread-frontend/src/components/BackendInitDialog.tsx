import { useState } from 'react'
import { AlertTriangle, Clipboard, Loader2, RefreshCw, RotateCcw, Stethoscope } from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useBackendEvents } from '@/components/BackendHealth/useBackendEvents'
import type { BackendStartupStatus } from '@/hooks/useCheckBackend'

interface Props {
  open: boolean
  status: BackendStartupStatus
  attempt: number
  error: string
  onRetry: () => void
}

function apiLabel() {
  return `${String(import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')}/sys_health`
}

function BackendInitDialog({ open, status, attempt, error, onRetry }: Props) {
  const [showDiagnostics, setShowDiagnostics] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const [copied, setCopied] = useState(false)
  const backend = useBackendEvents()
  const failed = status === 'failed'

  const restart = async () => {
    setRestarting(true)
    try {
      await backend.restart()
      onRetry()
    }
    finally {
      setRestarting(false)
    }
  }

  const copyLogs = async () => {
    setCopied(await backend.copyLogs())
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <Dialog open={open}>
      <DialogContent className="sm:max-w-xl" showCloseButton={false} onEscapeKeyDown={event => event.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {failed
              ? <AlertTriangle className="h-5 w-5 text-red-600" />
              : <Loader2 className="h-5 w-5 animate-spin text-blue-600" />}
            {failed ? 'FastRead 后端未能启动' : '正在连接 FastRead 后端'}
          </DialogTitle>
          <DialogDescription>
            {failed
              ? '主界面没有卡死：后端健康检查已停止自动重试。你可以立即重试，或先查看诊断信息。'
              : `正在执行健康检查（第 ${Math.max(attempt, 1)} / 4 次），通常只需几秒。`}
          </DialogDescription>
        </DialogHeader>

        {failed && (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error || '无法连接后端健康检查接口。'}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button onClick={onRetry} disabled={!failed}>
            <RefreshCw className="mr-1.5 h-4 w-4" />立即重试
          </Button>
          {backend.isTauri && (
            <Button variant="outline" onClick={restart} disabled={restarting}>
              {restarting
                ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                : <RotateCcw className="mr-1.5 h-4 w-4" />}
              重启后端
            </Button>
          )}
          <Button variant="outline" onClick={() => setShowDiagnostics(value => !value)}>
            <Stethoscope className="mr-1.5 h-4 w-4" />
            {showDiagnostics ? '收起诊断' : '查看诊断 / 日志'}
          </Button>
        </div>

        {showDiagnostics && (
          <div className="space-y-3 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
            <div>
              <div className="font-semibold text-slate-800">健康检查地址</div>
              <code className="mt-1 block break-all rounded bg-white px-2 py-1.5">{apiLabel()}</code>
            </div>
            <p>
              {backend.isTauri
                ? `桌面后端状态：${backend.status === 'terminated' ? `已退出（${backend.exitCode ?? '未知退出码'}）` : '进程已启动但健康检查未通过'}。`
                : 'Web 模式不会自动启动 Python 后端；请确认后端服务正在运行，并检查 VITE_API_BASE_URL 或 Vite 代理配置。'}
            </p>
            {backend.isTauri && (
              <>
                <div className="max-h-36 overflow-y-auto rounded bg-slate-950 p-2 font-mono text-[11px] text-slate-100">
                  {backend.logs.length
                    ? backend.logs.slice(-30).map((entry, index) => (
                        <div key={`${entry.ts}-${index}`} className={entry.level === 'error' ? 'text-red-300' : ''}>
                          {entry.text}
                        </div>
                      ))
                    : <span className="text-slate-400">暂未收到后端日志；可尝试重启后再次检查。</span>}
                </div>
                <Button size="sm" variant="outline" onClick={copyLogs} disabled={!backend.logs.length}>
                  <Clipboard className="mr-1.5 h-3.5 w-3.5" />{copied ? '日志已复制' : '复制日志'}
                </Button>
              </>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default BackendInitDialog
