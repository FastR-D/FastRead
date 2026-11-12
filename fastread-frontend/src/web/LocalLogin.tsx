import { Alert, Button, TextField } from '@fastrd/ui-react'
import { API_BASE } from './urls'
import { useEffect, useState, type FormEvent } from 'react'
export default function LocalLogin() {
  const [mode, setMode] = useState<'login' | 'register' | 'recover'>(() =>
    new URLSearchParams(window.location.search).get('fastcas') === 'register' ? 'register' : 'login'
  )
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(
    new URLSearchParams(window.location.search).get('fastcas') === 'failed'
      ? 'FastCAS 登录未完成。请使用原方式登录，并在账号设置中认证；也可稍后重试。'
      : ''
  )
  const [fastcas, setFastcas] = useState(false)
  useEffect(() => {
    if (mode !== 'register') return
    const controller = new AbortController()
    fetch(`${API_BASE}/auth/fastcas/registration`, { signal: controller.signal })
      .then(async r => {
        const value = await r.json()
        if (!r.ok) throw new Error(value.detail)
        return value
      })
      .then(value => {
        setEmail(value.email)
        setDisplayName(value.display_name)
      })
      .catch(error => {
        if (!controller.signal.aborted) setMessage(error.message)
      })
    return () => controller.abort()
  }, [mode])
  useEffect(() => {
    fetch(`${API_BASE}/auth/fastcas/available`)
      .then(r => (r.ok ? r.json() : null))
      .then(v => {
        const enabled = v?.enabled === true && v.login_enabled !== false
        setFastcas(enabled)
        const query = new URLSearchParams(window.location.search)
        if (enabled && query.get('auth') === 'register' && query.get('fastcas') !== 'register')
          window.location.replace(`${API_BASE}/auth/fastcas/login`)
      })
      .catch(() => {})
  }, [])
  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      const init = await fetch(`${API_BASE}/auth/session-init`, { credentials: 'same-origin' })
      if (!init.ok) throw new Error('无法初始化登录，请稍后重试')
      const { csrf } = await init.json()
      const response = await fetch(
        `${API_BASE}/auth/${mode === 'register' ? 'fastcas/registration' : mode}`,
        {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
          body: JSON.stringify(
            mode === 'login'
              ? { email, password }
              : mode === 'register'
                ? { email, display_name: displayName, password }
                : { token, password }
          ),
        }
      )
      const result = await response.json()
      if (!response.ok)
        throw new Error(typeof result.detail === 'string' ? result.detail : '请检查输入内容')
      if (mode === 'register') window.location.assign(result.url)
      else if (mode === 'login') {
        const url = new URL(window.location.href)
        url.searchParams.delete('fastcas')
        window.location.assign(url.href)
      } else {
        setMode('login')
        setPassword('')
        setToken('')
        setMessage('密码已设置，请使用邮箱和密码登录。')
      }
    } catch (error) {
      setMessage((error as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section
      aria-label="FastRead 登录"
      className="web-login fastui-section grid w-full max-w-md gap-4 p-6"
    >
      <div className="wordmark font-semibold">FastRead</div>
      <h1 className="fastui-heading m-0 text-xl">
        {mode === 'login' ? '登录资料库' : mode === 'register' ? '完善 FastRead 账号' : '恢复账号'}
      </h1>
      <form onSubmit={submit} className="grid min-w-0 gap-3">
        {mode === 'register' && (
          <label className="fastui-field">
            姓名
            <TextField
              maxLength={120}
              value={displayName}
              onChange={e => setDisplayName(e.target.value)}
            />
          </label>
        )}
        {mode !== 'recover' ? (
          <label className="fastui-field">
            邮箱
            <TextField
              type="email"
              autoComplete="username"
              required
              maxLength={254}
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full"
            />
          </label>
        ) : (
          <label className="fastui-field">
            恢复凭证
            <TextField
              required
              maxLength={256}
              value={token}
              onChange={e => setToken(e.target.value)}
              className="w-full"
            />
          </label>
        )}
        <label className="fastui-field">
          {mode === 'login' ? '密码' : '新密码（至少 12 个字符）'}
          <TextField
            type="password"
            required
            minLength={mode === 'login' ? 1 : 12}
            maxLength={256}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            value={password}
            onChange={e => setPassword(e.target.value)}
            className="w-full"
          />
        </label>
        <Button loading={busy} disabled={busy} type="submit" variant="primary">
          {busy ? '处理中…' : '确认'}
        </Button>
      </form>
      {message && <Alert>{message}</Alert>}
      {fastcas && mode === 'login' && (
        <a href={`${API_BASE}/auth/fastcas/login`} className="fastui-link break-words">
          使用 FastCAS 登录
        </a>
      )}
      <nav className="flex flex-wrap gap-2" aria-label="登录方式">
        {(['login', 'recover'] as const)
          .filter(v => v !== mode)
          .map(v => (
            <Button
              key={v}
              disabled={busy}
              onClick={() => {
                setMode(v)
                setMessage('')
                setPassword('')
                setToken('')
              }}
              type="button"
              variant="quiet"
            >
              {v === 'login' ? '返回登录' : '恢复账号'}
            </Button>
          ))}
      </nav>
      {mode === 'recover' && (
        <p className="m-0 leading-relaxed break-words">请联系此实例管理员获取一次性凭证。</p>
      )}
    </section>
  )
}
