import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BookOpen, Check, FileUp, Loader2, RefreshCw } from 'lucide-react'
import { addModel, addProvider, fetchEnableModels, getProviderList, testConnection, type EnabledModel } from '@/services/model'
import { ingest_paper_pdf, ingest_paper_url, type TaskSnapshot } from '@/services/note'
import { useTaskStore } from '@/store/taskStore'
import { paperImportModelFields } from '@/utils/paperImport'
import { buildWorkspaceSearch } from '@/utils/workspaceNavigation'
import logo from '@/assets/icon.png'

const ONBOARD_KEY = 'fastread-onboarded'
export function isOnboarded(): boolean {
  return localStorage.getItem(ONBOARD_KEY) === '1'
}

function markOnboarded() {
  localStorage.setItem(ONBOARD_KEY, '1')
}

function errorMessage(error: unknown) {
  if (error && typeof error === 'object' && 'msg' in error) return String(error.msg)
  return error instanceof Error ? error.message : String(error)
}

const Onboarding = () => {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { applyTaskSnapshot, setCurrentTask } = useTaskStore()
  const [step, setStep] = useState(1)
  const [error, setError] = useState('')

  const [pinging, setPinging] = useState(false)
  const [backendOk, setBackendOk] = useState<boolean | null>(null)

  const [providerName, setProviderName] = useState('Qwen')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('https://dashscope.aliyuncs.com/compatible-mode/v1')
  const [modelName, setModelName] = useState('qwen-plus')
  const [configuredModel, setConfiguredModel] = useState<EnabledModel | null>(null)
  const [showModelForm, setShowModelForm] = useState(false)
  const [savingProvider, setSavingProvider] = useState(false)
  const [testingModel, setTestingModel] = useState(false)

  const [paperUrl, setPaperUrl] = useState('')
  const [importing, setImporting] = useState(false)
  const [importedTaskId, setImportedTaskId] = useState<string | null>(null)

  function next() {
    setError('')
    setStep(current => Math.min(4, current + 1))
  }

  function prev() {
    setError('')
    setStep(current => Math.max(1, current - 1))
  }

  async function checkBackend() {
    setPinging(true)
    setBackendOk(null)
    setError('')
    try {
      await getProviderList()
      setBackendOk(true)
    }
    catch (nextError) {
      setBackendOk(false)
      setError(`后端检查失败：${errorMessage(nextError)}`)
    }
    finally {
      setPinging(false)
    }
  }

  useEffect(() => {
    if (step === 1) checkBackend()
  }, [step])

  useEffect(() => {
    if (step !== 2) return
    let cancelled = false
    ;(async () => {
      try {
        const models = await fetchEnableModels()
        if (!cancelled && models.length) {
          setConfiguredModel(models[0])
          setShowModelForm(false)
        }
        else if (!cancelled) {
          setShowModelForm(true)
        }
      }
      catch {
        if (!cancelled) setShowModelForm(true)
      }
    })()
    return () => { cancelled = true }
  }, [step])

  async function verifyConfiguredModel() {
    if (!configuredModel) return
    setTestingModel(true)
    setError('')
    try {
      await testConnection({ id: configuredModel.provider_id })
      next()
    }
    catch (nextError) {
      setError(`模型连通性测试失败：${errorMessage(nextError)}`)
    }
    finally {
      setTestingModel(false)
    }
  }

  async function saveProvider() {
    setError('')
    if (!apiKey.trim() || !baseUrl.trim() || !providerName.trim() || !modelName.trim()) {
      setError('请完整填写供应商、API 地址、API Key 和模型名。')
      return
    }
    setSavingProvider(true)
    try {
      const providerId = await addProvider({
        name: providerName.trim(),
        api_key: apiKey.trim(),
        base_url: baseUrl.trim(),
        type: 'custom',
        logo: 'custom',
      })
      if (!providerId) throw new Error('后端未返回 provider id')
      const modelResult = await addModel({ provider_id: providerId, model_name: modelName.trim() })
      await testConnection({ id: providerId })
      setConfiguredModel({
        id: String(modelResult?.id || `${providerId}:${modelName.trim()}`),
        provider_id: providerId,
        model_name: modelName.trim(),
      })
      next()
    }
    catch (nextError) {
      setError(`模型保存或连通性测试失败：${errorMessage(nextError)}`)
    }
    finally {
      setSavingProvider(false)
    }
  }

  function registerPaper(snapshot: TaskSnapshot, sourceLabel: string) {
    const modelFields = paperImportModelFields(configuredModel)
    applyTaskSnapshot(snapshot, {
      source_url: sourceLabel,
      filename: snapshot.paperDocument?.filename,
      ...modelFields,
    })
    setCurrentTask(snapshot.id)
    setImportedTaskId(snapshot.id)
  }

  async function importPdf(file?: File) {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('请选择 PDF 论文。')
      return
    }
    setImporting(true)
    setError('')
    try {
      const snapshot = await ingest_paper_pdf({
        file,
        ...paperImportModelFields(configuredModel),
      })
      registerPaper(snapshot, file.name)
      next()
    }
    catch (nextError) {
      setError(`PDF 导入失败：${errorMessage(nextError)}`)
    }
    finally {
      setImporting(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function importUrl() {
    if (!paperUrl.trim()) {
      setError('请输入论文详情页或 PDF URL。')
      return
    }
    setImporting(true)
    setError('')
    try {
      const snapshot = await ingest_paper_url({
        url: paperUrl.trim(),
        ...paperImportModelFields(configuredModel),
      })
      registerPaper(snapshot, paperUrl.trim())
      next()
    }
    catch (nextError) {
      setError(`论文 URL 导入失败：${errorMessage(nextError)}`)
    }
    finally {
      setImporting(false)
    }
  }

  function finish() {
    markOnboarded()
    if (importedTaskId) {
      navigate(`/workspace?${buildWorkspaceSearch({ taskId: importedTaskId, view: 'source' })}`, { replace: true })
      return
    }
    navigate('/workspace', { replace: true })
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 p-6">
      <div className="w-full max-w-2xl rounded-xl border border-slate-200 bg-white p-7 shadow-xl">
        <div className="mb-5 flex items-center gap-3">
          <img src={logo} alt="FastRead" className="h-11 w-11 rounded-lg" />
          <div>
            <h1 className="text-xl font-bold text-slate-950">欢迎使用 FastRead</h1>
            <p className="text-sm text-slate-500">从一篇论文开始，建立可回到原文页码的阅读闭环。</p>
          </div>
        </div>

        <ol aria-label="首次使用步骤" className="mb-7 grid grid-cols-4 gap-2 text-center text-[11px] text-slate-500">
          {['后端', '模型（可选）', '导入论文', '完成'].map((label, index) => {
            const number = index + 1
            const complete = step > number
            return (
              <li key={label} className="flex flex-col items-center gap-1.5">
                <span className={`flex h-7 w-7 items-center justify-center rounded-full border font-semibold ${
                  step >= number ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-300 bg-white text-slate-400'
                }`}>
                  {complete ? <Check className="h-4 w-4" /> : number}
                </span>
                <span className={step === number ? 'font-semibold text-slate-800' : ''}>{label}</span>
              </li>
            )
          })}
        </ol>

        {step === 1 && (
          <section className="space-y-4">
            <div>
              <h2 className="font-semibold text-slate-900">第 1 步 · 确认本地服务</h2>
              <p className="mt-1 text-sm leading-6 text-slate-600">桌面版会自动启动后端；Web 版需要连接已经运行的后端服务。</p>
            </div>
            {pinging && <Status tone="neutral"><Loader2 className="h-4 w-4 animate-spin" />正在检查后端…</Status>}
            {backendOk === true && <Status tone="success"><Check className="h-4 w-4" />后端已就绪，可以读取与解析论文。</Status>}
            {backendOk === false && <Status tone="error">后端暂不可用。请先处理启动页给出的诊断，再回来重试。</Status>}
            {error && <ErrorText>{error}</ErrorText>}
            <div className="flex justify-end gap-2">
              <button className="rounded border px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50" onClick={checkBackend} disabled={pinging}>
                <RefreshCw className="mr-1 inline h-3.5 w-3.5" />重新检查
              </button>
              <PrimaryButton disabled={!backendOk} onClick={next}>下一步</PrimaryButton>
            </div>
          </section>
        )}

        {step === 2 && (
          <section className="space-y-4">
            <div>
              <h2 className="font-semibold text-slate-900">第 2 步 · 阅读模型（可选）</h2>
              <p className="mt-1 text-sm leading-6 text-slate-600">导入 PDF、保留分页原文和手动阅读不需要 API Key。阅读报告和持续追问需要模型，可以现在配置，也可以稍后再配。</p>
            </div>
            {configuredModel && !showModelForm && (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
                <div className="text-sm font-semibold text-emerald-900">已发现模型：{configuredModel.model_name}</div>
                <p className="mt-1 text-xs text-emerald-800">点击验证后继续；API Key 不会显示在这里。</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <PrimaryButton disabled={testingModel} onClick={verifyConfiguredModel}>
                    {testingModel ? '验证中…' : '验证模型并下一步'}
                  </PrimaryButton>
                  <button className="rounded border border-emerald-300 bg-white px-3 py-1.5 text-sm text-emerald-800" onClick={() => setShowModelForm(true)}>
                    配置新模型
                  </button>
                </div>
              </div>
            )}
            {showModelForm && (
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="供应商名" value={providerName} onChange={setProviderName} />
                <Field label="模型名" value={modelName} onChange={setModelName} placeholder="qwen-plus" />
                <div className="sm:col-span-2"><Field label="OpenAI 兼容 API 地址" value={baseUrl} onChange={setBaseUrl} /></div>
                <div className="sm:col-span-2"><Field label="API Key" value={apiKey} onChange={setApiKey} type="password" /></div>
              </div>
            )}
            {error && <ErrorText>{error}</ErrorText>}
            <div className="flex justify-between gap-2">
              <button className="text-sm text-slate-500 hover:text-slate-900" onClick={prev}>上一步</button>
              <div className="flex flex-wrap justify-end gap-2">
                <button className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50" onClick={next} disabled={savingProvider || testingModel}>
                  暂不配置，先导入论文
                </button>
                {showModelForm && <PrimaryButton disabled={savingProvider} onClick={saveProvider}>{savingProvider ? '保存并验证中…' : '保存、验证并继续'}</PrimaryButton>}
              </div>
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="space-y-4">
            <div>
              <h2 className="font-semibold text-slate-900">第 3 步 · 导入第一篇论文</h2>
              <p className="mt-1 text-sm leading-6 text-slate-600">导入 PDF，或粘贴可访问的论文详情页 / PDF URL。FastRead 会保留分页文本，供报告和追问回到原文。</p>
            </div>
            <input ref={fileInputRef} type="file" accept="application/pdf,.pdf" className="hidden" onChange={event => importPdf(event.target.files?.[0])} />
            <button
              type="button"
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-blue-300 bg-blue-50 px-4 py-5 text-sm font-semibold text-blue-800 hover:bg-blue-100 disabled:opacity-50"
              onClick={() => fileInputRef.current?.click()}
              disabled={importing}
            >
              {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
              选择本地 PDF
            </button>
            <div className="flex gap-2">
              <input
                value={paperUrl}
                onChange={event => setPaperUrl(event.target.value)}
                className="min-w-0 flex-1 rounded border border-slate-300 px-3 py-2 text-sm"
                placeholder="https://arxiv.org/abs/... 或 PDF URL"
              />
              <PrimaryButton disabled={importing || !paperUrl.trim()} onClick={importUrl}>导入 URL</PrimaryButton>
            </div>
            {error && <ErrorText>{error}</ErrorText>}
            <div className="flex justify-between gap-2">
              <button className="text-sm text-slate-500 hover:text-slate-900" onClick={prev}>上一步</button>
              <button className="text-sm text-slate-500 hover:text-slate-900" onClick={next}>暂不导入，进入工作台</button>
            </div>
          </section>
        )}

        {step === 4 && (
          <section className="space-y-5 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
              <BookOpen className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-950">论文阅读工作台已准备好</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                {importedTaskId
                  ? configuredModel
                    ? '首篇论文已经导入。接下来逐页阅读、生成关键问题报告，再写下自己的个人总结。'
                    : '首篇论文已经导入，可以立即逐页阅读。需要生成报告或持续追问时，再到设置中启用模型。'
                  : '你可以在工作台随时导入 PDF 或论文 URL；视频转写和 Cookie 不再是首次使用的前置条件。'}
              </p>
            </div>
            <PrimaryButton onClick={finish}>进入论文工作台</PrimaryButton>
          </section>
        )}
      </div>
    </div>
  )
}

function PrimaryButton({ children, disabled, onClick }: { children: React.ReactNode; disabled?: boolean; onClick: () => void }) {
  return <button className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50" disabled={disabled} onClick={onClick}>{children}</button>
}

function Field({ label, value, onChange, placeholder, type = 'text' }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string; type?: string }) {
  return (
    <label className="flex flex-col gap-1 text-sm text-slate-600">
      <span>{label}</span>
      <input type={type} value={value} onChange={event => onChange(event.target.value)} placeholder={placeholder} className="rounded border border-slate-300 px-2 py-1.5 text-slate-900" />
    </label>
  )
}

function Status({ children, tone }: { children: React.ReactNode; tone: 'neutral' | 'success' | 'error' }) {
  const tones = {
    neutral: 'border-slate-200 bg-slate-50 text-slate-700',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    error: 'border-red-200 bg-red-50 text-red-800',
  }
  return <div className={`flex items-center gap-2 rounded border p-3 text-sm ${tones[tone]}`}>{children}</div>
}

function ErrorText({ children }: { children: React.ReactNode }) {
  return <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{children}</div>
}

export default Onboarding
