import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Database, FolderOpen, Loader2, RefreshCw, Server, XCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { getDeployStatus, type DeployStatus } from '@/services/system'

export default function Monitor() {
  const [status, setStatus] = useState<DeployStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setStatus(await getDeployStatus())
      setLastUpdated(new Date())
    }
    catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '无法连接到后端服务')
      setStatus(null)
    }
    finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchStatus()
    const timer = window.setInterval(fetchStatus, 30000)
    return () => window.clearInterval(timer)
  }, [fetchStatus])

  const StatusBadge = ({ ok }: { ok: boolean }) => (
    <Badge variant={ok ? 'default' : 'destructive'} className={ok ? 'bg-emerald-600' : ''}>
      {ok ? <CheckCircle2 className="mr-1 h-3 w-3" /> : <XCircle className="mr-1 h-3 w-3" />}
      {ok ? '正常' : '异常'}
    </Badge>
  )

  return (
    <ScrollArea className="h-full overflow-y-auto bg-white">
      <div className="container mx-auto px-4 py-8">
        <div className="mb-8 flex items-center justify-between gap-4">
          <div><h1 className="text-2xl font-bold">运行状态</h1><p className="mt-1 text-sm text-muted-foreground">论文数据库、产物目录与本地后端</p></div>
          <div className="flex items-center gap-3">
            {lastUpdated && <span className="text-xs text-muted-foreground">{lastUpdated.toLocaleTimeString()}</span>}
            <Button variant="outline" size="sm" onClick={() => void fetchStatus()} disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}刷新
            </Button>
          </div>
        </div>
        {error && <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
        <div className="grid gap-5 md:grid-cols-3">
          <Card><CardHeader className="flex flex-row items-center justify-between"><CardTitle className="text-base"><Server className="mr-2 inline h-4 w-4" />本地后端</CardTitle>{status && <StatusBadge ok={status.backend.status === 'running'} />}</CardHeader><CardContent className="text-sm text-slate-600">端口 {status?.backend.port || '—'}</CardContent></Card>
          <Card><CardHeader className="flex flex-row items-center justify-between"><CardTitle className="text-base"><Database className="mr-2 inline h-4 w-4" />论文数据库</CardTitle>{status && <StatusBadge ok={status.database.available} />}</CardHeader><CardContent className="break-all font-mono text-xs text-slate-600">{status?.database.path || '—'}</CardContent></Card>
          <Card><CardHeader className="flex flex-row items-center justify-between"><CardTitle className="text-base"><FolderOpen className="mr-2 inline h-4 w-4" />论文存储</CardTitle>{status && <StatusBadge ok={status.storage.paper_results && status.storage.uploads} />}</CardHeader><CardContent className="text-sm text-slate-600">分页产物：{status?.storage.paper_results ? '可写' : '异常'} · 上传目录：{status?.storage.uploads ? '可写' : '异常'}</CardContent></Card>
        </div>
        {status && <div className="mt-6 rounded-md border border-slate-200 bg-slate-50 p-3 font-mono text-xs text-slate-500">Python {status.runtime.python} · {status.runtime.platform}</div>}
      </div>
    </ScrollArea>
  )
}
