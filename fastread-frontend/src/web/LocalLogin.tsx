import { API_BASE } from './urls'
import { useEffect, useState, type FormEvent } from 'react'

export default function LocalLogin() {
  const [mode, setMode] = useState<'login' | 'register' | 'recover'>(() => new URLSearchParams(window.location.search).get('fastcas') === 'register' ? 'register' : 'login')
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(new URLSearchParams(window.location.search).get('fastcas') === 'failed' ? 'FastCAS 登录未完成。请使用原方式登录，并在账号设置中认证；也可稍后重试。' : '')
  const [fastcas, setFastcas] = useState(false)
  useEffect(() => { if (mode === 'register') fetch(`${API_BASE}/auth/fastcas/registration`).then(async r => { const value = await r.json(); if (!r.ok) throw new Error(value.detail); return value }).then(p => { setEmail(p.email); setDisplayName(p.display_name) }).catch(e => setMessage(e.message)) }, [mode])
  useEffect(() => { fetch(`${API_BASE}/auth/fastcas/available`).then(r => r.ok ? r.json() : null).then(v => {
    const enabled = v?.enabled === true && v.login_enabled !== false
    setFastcas(enabled)
    if (enabled && new URLSearchParams(window.location.search).get('auth') === 'register' && mode !== 'register') window.location.replace(`${API_BASE}/auth/fastcas/login`)
  }).catch(() => {}) }, [])
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage('')
    try {
      const init = await fetch(`${API_BASE}/auth/session-init`, { credentials: 'same-origin' })
      if (!init.ok) throw new Error('无法初始化登录，请稍后重试')
      const { csrf } = await init.json()
      const response = await fetch(`${API_BASE}/auth/${mode === 'register' ? 'fastcas/registration' : mode}`, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify(mode === 'login' ? { email, password } : mode === 'register' ? { email, display_name: displayName, password } : { token, password }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '请检查输入内容')
      if (mode === 'register') window.location.assign(result.url)
      else if (mode === 'login') { const url = new URL(window.location.href); url.searchParams.delete('fastcas'); window.location.assign(url.href) }
      else { setMode('login'); setPassword(''); setToken(''); setMessage('密码已设置，请使用邮箱和密码登录。') }
    } catch (error) { setMessage((error as Error).message) }
    finally { setBusy(false) }
  }
  return <main className="web-login"><div className="wordmark">FastRead</div>
    <h1>{mode === 'login' ? '登录资料库' : mode === 'register' ? '完善 FastRead 账号' : '恢复账号'}</h1>
    <form onSubmit={submit}>
      {mode === 'register' && <label>姓名<input maxLength={120} value={displayName} onChange={e => setDisplayName(e.target.value)} /></label>}
      {mode !== 'recover' ? <label>邮箱<input type="email" autoComplete="username" required maxLength={254} value={email} onChange={e => setEmail(e.target.value)} /></label>
        : <label>恢复凭证<input required maxLength={256} value={token} onChange={e => setToken(e.target.value)} /></label>}
      <label>{mode === 'login' ? '密码' : '新密码（至少 12 个字符）'}<input type="password" required minLength={mode === 'login' ? 1 : 12} maxLength={256} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={e => setPassword(e.target.value)} /></label>
      <button disabled={busy} type="submit">{busy ? '处理中…' : '确认'}</button>
    </form>
    {message && <p role="status">{message}</p>}
    {fastcas && mode === 'login' && <a href={`${API_BASE}/auth/fastcas/login`}>使用 FastCAS 登录</a>}
    <nav>{(['login', 'recover'] as const).filter(v => v !== mode).map(v => <button key={v} disabled={busy} onClick={() => { setMode(v); setMessage(''); setPassword(''); setToken('') }}>{v === 'login' ? '已有账号，返回登录后绑定' : '恢复账号'}</button>)}</nav>
    {mode === 'recover' && <p>请联系此实例管理员获取一次性恢复凭证。</p>}
  </main>
}
