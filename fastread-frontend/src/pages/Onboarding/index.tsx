import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { addProvider, addModel, getProviderList, testConnection } from '@/services/model'
import { updateTranscriberConfig } from '@/services/transcriber'
import logo from '@/assets/icon.png'

// 桌面端首启 4 步引导。完成后写 localStorage('fastread-onboarded') = '1'，路由守卫不再拦。
//
// 1. 后端连通性自检
// 2. LLM 供应商 + 模型（最简：只引导填一个 OpenAI 兼容供应商 + 一个 model 名）
// 3. 转写引擎选择（优先中文场景友好的在线引擎）
// 4. （可选）Cookie 同步说明（主要面向抖音精选等需要登录态的页面）

const ONBOARD_KEY = 'fastread-onboarded'
const LEGACY_ONBOARD_KEY = 'bilinote-onboarded'

export function isOnboarded(): boolean {
  return localStorage.getItem(ONBOARD_KEY) === '1' || localStorage.getItem(LEGACY_ONBOARD_KEY) === '1'
}

function markOnboarded() {
  localStorage.setItem(ONBOARD_KEY, '1')
}

const Onboarding = () => {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [error, setError] = useState('')

  // step 1
  const [pinging, setPinging] = useState(false)
  const [backendOk, setBackendOk] = useState<boolean | null>(null)

  // step 2
  const [providerName, setProviderName] = useState('Qwen')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('https://dashscope.aliyuncs.com/compatible-mode/v1')
  const [modelName, setModelName] = useState('qwen-plus')
  const [savingProvider, setSavingProvider] = useState(false)

  // step 3
  const [transcriberType, setTranscriberType] = useState<string>('bcut')
  const [savingTranscriber, setSavingTranscriber] = useState(false)

  function next() {
    setError('')
    setStep(s => s + 1)
  }
  function prev() {
    setError('')
    setStep(s => Math.max(1, s - 1))
  }

  // step 1: ping 后端
  useEffect(() => {
    if (step !== 1) return
    let cancelled = false
    ;(async () => {
      setPinging(true)
      try {
        await getProviderList()
        if (!cancelled) setBackendOk(true)
      }
      catch {
        if (!cancelled) setBackendOk(false)
      }
      finally {
        if (!cancelled) setPinging(false)
      }
    })()
    return () => { cancelled = true }
  }, [step])

  async function saveProvider() {
    setError('')
    if (!apiKey.trim()) { setError('请填 API Key'); return }
    if (!baseUrl.trim()) { setError('请填 API 地址'); return }
    if (!providerName.trim()) { setError('请填供应商名'); return }
    if (!modelName.trim()) { setError('请填模型名'); return }
    setSavingProvider(true)
    try {
      // 复用桌面 web 端的 add_provider；type 必须是 'custom'（backend 强制）
      const res: any = await addProvider({
        name: providerName.trim(),
        api_key: apiKey.trim(),
        base_url: baseUrl.trim(),
        type: 'custom',
        logo: 'custom',
      })
      const newId = (res?.data ?? res) as string | undefined
      if (!newId) throw new Error('后端未返回 provider id')

      // 加一个默认 model
      await addModel({ provider_id: newId, model_name: modelName.trim() })

      // 测试连通
      try { await testConnection({ id: newId }) }
      catch (e: any) {
        // 测试失败不阻断流程，让用户自己决定继续
        console.warn('测试连接失败：', e?.message ?? e)
      }
      next()
    }
    catch (e: any) {
      setError(`保存失败：${e?.message ?? e}`)
    }
    finally {
      setSavingProvider(false)
    }
  }

  async function saveTranscriber() {
    setError('')
    setSavingTranscriber(true)
    try {
      // fast-whisper / mlx-whisper 需指定 model size；在线 (groq/bcut) 不用
      const needsSize = transcriberType === 'fast-whisper' || transcriberType === 'mlx-whisper'
      await updateTranscriberConfig({
        transcriber_type: transcriberType,
        ...(needsSize ? { whisper_model_size: 'tiny' } : {}),
      } as any)
      next()
    }
    catch (e: any) {
      setError(`保存失败：${e?.message ?? e}`)
    }
    finally {
      setSavingTranscriber(false)
    }
  }

  function finish() {
    markOnboarded()
    navigate('/', { replace: true })
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-pink-50 p-6">
      <div className="w-full max-w-xl rounded-xl border bg-white p-6 shadow-lg">
        <div className="flex items-center gap-3 mb-4">
          <img src={logo} alt="logo" className="h-10 w-10" />
          <div>
            <h1 className="text-xl font-bold">欢迎使用 FastRead</h1>
            <p className="text-xs text-gray-500">先把运行环境接好，再开始整理抖音精选知识视频。</p>
          </div>
        </div>

        {/* Stepper */}
        <div className="mb-5 flex items-center gap-2 text-xs text-gray-500">
          {[1, 2, 3, 4].map(s => (
            <div key={s} className="flex items-center gap-2">
              <div
                className={`flex h-6 w-6 items-center justify-center rounded-full border ${step >= s ? 'border-blue-600 bg-blue-600 text-white' : 'border-gray-300 bg-white text-gray-400'}`}
              >{s}</div>
              {s < 4 && <div className={`h-px w-8 ${step > s ? 'bg-blue-600' : 'bg-gray-300'}`} />}
            </div>
          ))}
        </div>

        {step === 1 && (
          <section className="flex flex-col gap-3">
            <h2 className="font-semibold">第 1 步 · 后端连通性</h2>
            <p className="text-sm text-gray-600">桌面端会自动启动 Python 后端进程。检查连通中…</p>
            {pinging && <div className="text-sm text-gray-500">检测中…</div>}
            {backendOk === true && <div className="rounded bg-green-50 p-2 text-sm text-green-700">✓ 后端已就绪</div>}
            {backendOk === false && (
              <div className="rounded bg-red-50 p-2 text-sm text-red-700">
                ✗ 暂时连不上后端。可能正在初始化（首次启动会下载依赖），等 1-2 分钟再试。
                右下角的「后端」状态点会持续监控。
              </div>
            )}
            <div className="flex gap-2 justify-end">
              <button className="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50" disabled={!backendOk} onClick={next}>
                下一步
              </button>
            </div>
          </section>
        )}

        {step === 2 && (
          <section className="flex flex-col gap-3">
            <h2 className="font-semibold">第 2 步 · 模型供应商</h2>
            <p className="text-sm text-gray-600">当前项目优先建议中文模型供应商。填一个 OpenAI 兼容接口即可，推荐 Qwen / DeepSeek。</p>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-gray-600">供应商名（自取）</span>
              <input className="input border rounded px-2 py-1" value={providerName} onChange={e => setProviderName(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-gray-600">API 地址</span>
              <input className="input border rounded px-2 py-1" value={baseUrl} onChange={e => setBaseUrl(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-gray-600">API Key</span>
              <input type="password" className="input border rounded px-2 py-1" value={apiKey} onChange={e => setApiKey(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-gray-600">模型名（如 qwen-plus / qwen3.6-plus / deepseek-chat）</span>
              <input className="input border rounded px-2 py-1" value={modelName} onChange={e => setModelName(e.target.value)} />
            </label>
            {error && <div className="text-xs text-red-600">{error}</div>}
            <div className="flex gap-2 justify-between">
              <button className="text-sm text-gray-500 hover:text-gray-800" onClick={prev}>上一步</button>
              <button className="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50" disabled={savingProvider} onClick={saveProvider}>
                {savingProvider ? '保存中…' : '保存并下一步'}
              </button>
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="flex flex-col gap-3">
            <h2 className="font-semibold">第 3 步 · 音频转写引擎</h2>
            <p className="text-sm text-gray-600">把视频音频转成文字。当前场景以中文知识视频为主，优先建议在线转写。</p>
            <div className="grid gap-2">
              {[
                { value: 'bcut', title: '必剪（在线，推荐）', desc: '中文场景友好，无需本地模型，适合作为当前默认选项。' },
                { value: 'groq', title: 'Groq（在线，通用）', desc: '速度快，适合通用或英文内容；对当前产品不是首选。' },
                { value: 'fast-whisper', title: 'Faster Whisper（本地）', desc: '完全离线但首次需下载 ~75MB（tiny）至 ~3GB（large-v3）的模型。CPU 慢。' },
              ].map(opt => (
                <label key={opt.value} className={`flex gap-3 p-3 rounded border cursor-pointer ${transcriberType === opt.value ? 'border-blue-600 bg-blue-50' : 'border-gray-200 hover:border-gray-300'}`}>
                  <input type="radio" name="transcriber" value={opt.value} checked={transcriberType === opt.value} onChange={e => setTranscriberType(e.target.value)} />
                  <div>
                    <div className="text-sm font-medium">{opt.title}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{opt.desc}</div>
                  </div>
                </label>
              ))}
            </div>
            {error && <div className="text-xs text-red-600">{error}</div>}
            <div className="flex gap-2 justify-between">
              <button className="text-sm text-gray-500 hover:text-gray-800" onClick={prev}>上一步</button>
              <button className="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50" disabled={savingTranscriber} onClick={saveTranscriber}>
                {savingTranscriber ? '保存中…' : '保存并下一步'}
              </button>
            </div>
          </section>
        )}

        {step === 4 && (
          <section className="flex flex-col gap-3">
            <h2 className="font-semibold">第 4 步 · Cookie 同步（可选）</h2>
            <p className="text-sm text-gray-600">
              当前项目优先面向 <strong>抖音精选</strong> 页面。遇到需要登录态的内容时，在浏览器登录抖音精选后，把 Cookie 复制到「下载配置」页同步到后端。
              <br />
              这一步可以先跳过，后面接真实页面时再补。
            </p>
            <div className="rounded bg-gray-50 p-3 text-xs text-gray-600">
              提示：普通 Web 页面不能直接读取其他站点 Cookie。前端现在提供剪贴板导入、状态校验和同步保存入口。
            </div>
            <div className="flex gap-2 justify-between">
              <button className="text-sm text-gray-500 hover:text-gray-800" onClick={prev}>上一步</button>
              <button className="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700" onClick={finish}>
                完成，进入 FastRead
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  )
}

export default Onboarding
