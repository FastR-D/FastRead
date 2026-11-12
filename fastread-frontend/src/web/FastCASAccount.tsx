import { Alert, Button, InspectorSection, Loading, Section, TextField } from '@fastrd/ui-react'
import { useCallback, useEffect, useState } from 'react'

type Status = {
  enabled: boolean
  link_enabled?: boolean
  link: null | {
    id: string
    subject: string
    state: string
    version: number
  }
}
export default function FastCASAccount({
  api,
}: {
  api: (path: string, method?: string, body?: unknown) => Promise<any>
}) {
  const [status, setStatus] = useState<Status | null>(null)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [email, setEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const load = useCallback(() => api('/auth/fastcas/status').then(setStatus), [api])
  useEffect(() => {
    void load().catch(e => setError(e.message))
  }, [load])
  async function act(action: 'link' | 'revoke' | 'reconcile') {
    setBusy(true)
    setError('')
    try {
      const result = await api(
        `/auth/fastcas/${action}`,
        'POST',
        action === 'reconcile' ? {} : { password }
      )
      setPassword('')
      if (action === 'link') window.location.assign(result.url)
      else await load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  async function saveCredential() {
    setBusy(true)
    setError('')
    try {
      await api('/auth/local-credential', 'POST', {
        email,
        password: newPassword,
        current_password: currentPassword,
      })
      window.location.reload()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
      setNewPassword('')
      setCurrentPassword('')
    }
  }
  return (
    <Section className="fastread-settings grid gap-4" aria-label="账号设置">
      <h2 className="fastui-heading m-0 text-base">FastCAS 账号认证</h2>
      {error && <Alert tone="danger">{error}</Alert>}
      {!status ? (
        <Loading label="正在读取账号状态…" />
      ) : !status.enabled ? (
        <p className="m-0 leading-relaxed break-words">未启用 FastCAS。</p>
      ) : (
        <>
          <p className="m-0 leading-relaxed break-words">
            {!status.link
              ? '尚未认证'
              : status.link.state === 'active'
                ? '已通过 FastCAS 认证'
                : '认证待完成'}
          </p>
          {status.link_enabled === false && !status.link && (
            <p className="m-0 leading-relaxed break-words">暂不开放认证。</p>
          )}
          <p className="m-0 leading-relaxed break-words">解除认证后可用本地密码登录。</p>
          <label className="fastui-field">
            当前账号密码
            <TextField
              type="password"
              autoComplete="current-password"
              maxLength={256}
              value={password}
              onChange={e => setPassword(e.target.value)}
            />
          </label>
          {!status.link ? (
            <Button
              loading={busy}
              disabled={status.link_enabled === false || !password}
              onClick={() => void act('link')}
            >
              认证当前账号
            </Button>
          ) : (
            <>
              {status.link.state === 'prepared' && (
                <Button
                  loading={busy}
                  disabled={status.link_enabled === false}
                  onClick={() => void act('reconcile')}
                >
                  重试完成认证
                </Button>
              )}
              <Button
                variant="danger"
                loading={busy}
                disabled={!password}
                onClick={() => void act('revoke')}
              >
                解除认证
              </Button>
            </>
          )}
        </>
      )}
      <InspectorSection label="设置本地登录邮箱和密码">
        <p className="m-0 leading-relaxed break-words">
          已有密码时请验证原密码。Research
          账号请先从原入口重新登录，并在五分钟内设置；账号和资料库保持不变。
        </p>
        <form
          onSubmit={e => {
            e.preventDefault()
            void saveCredential()
          }}
          className="grid min-w-0 gap-4"
        >
          <label className="fastui-field">
            登录邮箱
            <TextField
              type="email"
              autoComplete="username"
              required
              maxLength={254}
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
          </label>
          <label className="fastui-field">
            原密码（Research 首次设置可留空）
            <TextField
              type="password"
              autoComplete="current-password"
              maxLength={256}
              value={currentPassword}
              onChange={e => setCurrentPassword(e.target.value)}
            />
          </label>
          <label className="fastui-field">
            新密码
            <TextField
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              maxLength={256}
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
            />
          </label>
          <Button type="submit" loading={busy}>
            保存本地登录方式
          </Button>
        </form>
      </InspectorSection>
    </Section>
  )
}
