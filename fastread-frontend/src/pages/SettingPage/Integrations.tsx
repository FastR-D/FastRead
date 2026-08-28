import { useEffect, useState } from 'react'
import { CheckCircle2, Database, RefreshCw, WifiOff } from 'lucide-react'
import { getFastNewsCatalog, getFastWriteStatus } from '@/services/evidenceHub'

type IntegrationState = { ok: boolean; title: string; detail: string; meta?: string }

export default function IntegrationsPage() {
  const [fastNews, setFastNews] = useState<IntegrationState | null>(null)
  const [fastWrite, setFastWrite] = useState<IntegrationState | null>(null)
  const [loading, setLoading] = useState(false)

  const check = async () => {
    setLoading(true)
    const [news, write] = await Promise.allSettled([
      getFastNewsCatalog({ limit: 1 }),
      getFastWriteStatus(),
    ])
    if (news.status === 'fulfilled') {
      setFastNews({
        ok: !news.value.stale,
        title: news.value.stale ? '使用最后缓存目录' : 'FastNews 目录可用',
        detail: news.value.warning || `${news.value.total} 条公开候选`,
        meta: `commit ${news.value.commit} · ${news.value.updated_at}`,
      })
    }
    else setFastNews({ ok: false, title: 'FastNews 不可用', detail: '没有可用在线目录或本地缓存。' })
    if (write.status === 'fulfilled') {
      setFastWrite({ ok: write.value.available, title: write.value.available ? 'FastWrite 已连接' : 'FastWrite 未连接', detail: write.value.message || write.value.origin, meta: write.value.origin })
    }
    else setFastWrite({ ok: false, title: 'FastWrite 状态读取失败', detail: 'FastRead 仍可生成本地证据包。' })
    setLoading(false)
  }

  useEffect(() => { check() }, [])

  return (
    <div className="h-full overflow-y-auto bg-slate-50 p-8">
      <div className="mx-auto max-w-4xl">
        <div className="flex items-start justify-between gap-4">
          <div><h1 className="text-2xl font-semibold">外部连接</h1><p className="mt-2 text-sm text-slate-500">连接全部可选；关闭或离线时 FastRead 仍是完整的本地论文阅读器。</p></div>
          <button type="button" onClick={check} disabled={loading} className="secondary-button"><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />重新检查</button>
        </div>
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <StatusCard icon={Database} name="FastNews" state={fastNews} footer="固定读取 FastR-D/FastNews 公开 JSONL；不接受任意仓库 URL。" />
          <StatusCard icon={CheckCircle2} name="FastWrite" state={fastWrite} footer="默认仅允许 127.0.0.1:3003；远程 origin 必须在后端精确白名单。" />
        </div>
        <div className="mt-6 rounded-lg border border-slate-200 bg-white p-5 text-xs leading-6 text-slate-600">
          <h2 className="font-semibold text-slate-900">安全边界</h2>
          <p className="mt-2">外部请求只由 FastRead 后端发起。FastInsight 输入最多 1 MiB 且只按 JSON 解析；FastWrite 交接只创建 references/fastread/&lt;bundle-id&gt;/ 下的新文件，manifest.json 最后写入。</p>
        </div>
      </div>
    </div>
  )
}

function StatusCard({ icon: Icon, name, state, footer }: { icon: typeof Database; name: string; state: IntegrationState | null; footer: string }) {
  return <section className="rounded-lg border border-slate-200 bg-white p-5"><div className="flex items-center gap-3"><span className={`flex h-10 w-10 items-center justify-center rounded-full ${state?.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>{state?.ok ? <Icon className="h-5 w-5" /> : <WifiOff className="h-5 w-5" />}</span><div><h2 className="text-sm font-semibold">{name}</h2><p className="text-xs text-slate-500">{state?.title || '检查中…'}</p></div></div><p className="mt-4 text-xs leading-5 text-slate-600">{state?.detail || '正在读取状态'}</p>{state?.meta && <p className="mt-2 break-all font-mono text-[9px] text-slate-400">{state.meta}</p>}<p className="mt-4 border-t border-slate-100 pt-3 text-[10px] leading-4 text-slate-400">{footer}</p></section>
}
