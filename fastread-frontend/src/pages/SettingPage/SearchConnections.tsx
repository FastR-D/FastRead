import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { KeyRound, Network, Save, Server } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  getPaperSearchConfig,
  updatePaperSearchConfig,
  type PaperSearchConfig,
} from '@/services/system'

const emptyConfig: PaperSearchConfig = {
  paper_search_proxy_url: '',
  google_scholar_api_url: '',
  serpapi_api_key_configured: false,
  elasticsearch_url: '',
}

const inputClassName = 'w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:bg-slate-50'

export default function SearchConnectionsPage() {
  const [config, setConfig] = useState<PaperSearchConfig>(emptyConfig)
  const [serpApiKey, setSerpApiKey] = useState('')
  const [clearSerpApiKey, setClearSerpApiKey] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getPaperSearchConfig()
      .then(setConfig)
      .catch(() => toast.error('学术检索连接设置读取失败'))
      .finally(() => setLoading(false))
  }, [])

  const update = (field: keyof Pick<PaperSearchConfig, 'paper_search_proxy_url' | 'google_scholar_api_url' | 'elasticsearch_url'>, value: string) => {
    setConfig(current => ({ ...current, [field]: value }))
  }

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    try {
      const saved = await updatePaperSearchConfig({
        paper_search_proxy_url: config.paper_search_proxy_url,
        google_scholar_api_url: config.google_scholar_api_url,
        elasticsearch_url: config.elasticsearch_url,
        serpapi_api_key: serpApiKey || undefined,
        clear_serpapi_api_key: clearSerpApiKey,
      })
      setConfig(saved)
      setSerpApiKey('')
      setClearSerpApiKey(false)
      toast.success('学术检索连接设置已保存')
    }
    catch {
      toast.error('保存失败，请检查 URL 格式')
    }
    finally {
      setSaving(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-slate-50 p-8">
      <form className="mx-auto max-w-3xl" onSubmit={save}>
        <div>
          <h1 className="text-2xl font-semibold text-slate-950">学术检索连接</h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">代理地址属于当前用户，不能写死为开发者电脑的端口。这里填写你的代理软件实际监听地址；留空表示未配置。</p>
        </div>

        <section className="mt-7 rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950">
          <div className="flex items-start gap-3"><Network className="mt-0.5 h-5 w-5 shrink-0" /><div><h2 className="font-semibold">境内网络提醒</h2><p className="mt-1">arXiv、Google Scholar、OpenAlex、Semantic Scholar 等外部学术来源默认启用，但在中国大陆网络环境下请通过代理访问，不要直连。FastRead 只使用下方由你配置的代理，不猜测端口，也不会接管系统代理。</p></div></div>
        </section>

        <fieldset disabled={loading || saving} className="mt-6 space-y-5">
          <SettingField icon={Network} label="论文检索代理" envName="PAPER_SEARCH_PROXY_URL" help="支持 HTTP/HTTPS 代理 URL，例如 http://127.0.0.1:你的端口。代理端口以你的客户端设置为准；Clash/Mihomo 请填写 mixed/http 端口。">
            <input aria-label="PAPER_SEARCH_PROXY_URL" className={inputClassName} placeholder="http://127.0.0.1:你的端口" value={config.paper_search_proxy_url} onChange={event => update('paper_search_proxy_url', event.target.value)} />
          </SettingField>

          <SettingField icon={KeyRound} label="Google Scholar API" envName="GOOGLE_SCHOLAR_API_URL / SERPAPI_API_KEY" help="可填写自建 Scholar API 地址，或保存 SerpAPI Key。API Key 使用本机密钥保护存储，读取设置时绝不回显。">
            <div className="space-y-3">
              <input aria-label="GOOGLE_SCHOLAR_API_URL" className={inputClassName} placeholder="https://你的 Scholar API 地址" value={config.google_scholar_api_url} onChange={event => update('google_scholar_api_url', event.target.value)} />
              <input aria-label="SERPAPI_API_KEY" className={inputClassName} type="password" autoComplete="new-password" placeholder={config.serpapi_api_key_configured ? '已保存密钥；留空则保持不变' : '输入 SerpAPI API Key'} value={serpApiKey} onChange={event => { setSerpApiKey(event.target.value); setClearSerpApiKey(false) }} />
              {config.serpapi_api_key_configured && <label className="flex items-center gap-2 text-xs text-slate-600"><input type="checkbox" checked={clearSerpApiKey} onChange={event => { setClearSerpApiKey(event.target.checked); if (event.target.checked) setSerpApiKey('') }} />删除已保存的 SerpAPI Key</label>}
            </div>
          </SettingField>

          <SettingField icon={Server} label="Elasticsearch" envName="ELASTICSEARCH_URL" help="Elasticsearch 通常是本机或局域网服务，应直接连接，不会套用上面的外网代理。留空时使用 FastRead 本地索引。">
            <input aria-label="ELASTICSEARCH_URL" className={inputClassName} placeholder="http://127.0.0.1:9200" value={config.elasticsearch_url} onChange={event => update('elasticsearch_url', event.target.value)} />
          </SettingField>
        </fieldset>

        <div className="mt-6 flex justify-end"><button type="submit" disabled={loading || saving} className="primary-button"><Save className="h-4 w-4" />{saving ? '保存中…' : '保存连接设置'}</button></div>
      </form>
    </div>
  )
}

function SettingField({ icon: Icon, label, envName, help, children }: { icon: typeof Network; label: string; envName: string; help: string; children: ReactNode }) {
  return <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-start gap-3"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-700"><Icon className="h-4 w-4" /></span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-baseline gap-x-3 gap-y-1"><h2 className="font-semibold text-slate-900">{label}</h2><code className="text-[11px] text-slate-400">{envName}</code></div><p className="mt-1 text-xs leading-5 text-slate-500">{help}</p><div className="mt-4">{children}</div></div></div></section>
}
