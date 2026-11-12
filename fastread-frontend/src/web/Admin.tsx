import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Checkbox, EmptyState, Select, TextField } from '@fastrd/ui-react'

type Row = Record<string, any>
type Api = (path: string, method?: string, body?: unknown) => Promise<any>

export function UserManagement({ api, currentUser }: { api: Api; currentUser: Row }) {
  const [users, setUsers] = useState<Row[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [creating, setCreating] = useState(false)
  const load = useCallback(async () => { setUsers((await api('/admin/users')).items) }, [api])
  useEffect(() => { void load().catch(e => setError(e.message)).finally(() => setLoading(false)) }, [load])
  async function save(action: () => Promise<unknown>, message: string) {
    setBusy(true); setError(''); setNotice('')
    try { await action(); await load(); setNotice(message) } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return <section className="admin-page">
    <div className="section-heading"><div><h1>用户管理</h1><p>管理账号、工作区与访问权限。</p></div><Button onClick={() => setCreating(!creating)}>新增用户</Button></div>
    {error && <Alert tone="danger">{error}</Alert>}{notice && <Alert tone="success">{notice}</Alert>}
    {creating && <form className="admin-form" onSubmit={e => { e.preventDefault(); const form = e.currentTarget; const data = Object.fromEntries(new FormData(form)); void save(async () => { await api('/admin/users', 'POST', data); form.reset(); setCreating(false) }, '用户已创建') }}>
      <label>邮箱<TextField type="email" name="email" autoComplete="off" required /></label>
      <label>显示名称<TextField name="display_name" maxLength={80} required /></label>
      <label>初始密码<TextField type="password" name="password" autoComplete="new-password" minLength={12} maxLength={256} required /></label>
      <label>工作区名称<TextField name="workspace_name" maxLength={120} required /></label>
      <label>角色<Select name="role"><option value="user">普通用户</option><option value="admin">系统管理员</option></Select></label>
      <div className="toolbar"><Button type="submit" loading={busy}>创建用户</Button><Button variant="quiet" onClick={() => setCreating(false)}>取消</Button></div>
    </form>}
    {loading ? <p role="status">正在读取用户…</p> : <div className="fastui-table-scroll" role="region" aria-label="用户列表" tabIndex={0}><table className="admin-table"><thead><tr><th>用户</th><th>工作区</th><th>角色</th><th>状态</th><th>操作</th></tr></thead><tbody>{users.map(user => <tr key={user.id}><td><strong>{user.display_name || user.email}</strong><small>{user.email}</small></td><td>{user.workspace_name || user.workspace_id}</td><td><Select aria-label={`${user.display_name || user.email}的角色`} value={user.role} disabled={busy || user.id === currentUser.id} onChange={e => void save(() => api(`/admin/users/${user.id}`, 'PATCH', { role: e.target.value }), '角色已更新')}><option value="user">普通用户</option><option value="admin">系统管理员</option></Select></td><td><Badge tone={user.disabled ? 'warning' : 'success'}>{user.disabled ? '已停用' : '正常'}</Badge></td><td><Button variant="quiet" disabled={busy || user.id === currentUser.id} onClick={() => void save(() => api(`/admin/users/${user.id}`, 'PATCH', { disabled: !user.disabled }), user.disabled ? '用户已启用' : '用户已停用')}>{user.disabled ? '启用' : '停用'}</Button></td></tr>)}</tbody></table>{!users.length && <EmptyState title="暂无用户" />}</div>}
  </section>
}

export function Administration({ api }: { api: Api }) {
  const [providers, setProviders] = useState<Row[]>([])
  const [workspaces, setWorkspaces] = useState<Row[]>([])
  const [status, setStatus] = useState<Row | null>(null)
  const [assigned, setAssigned] = useState<string[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    const [models, spaces, health] = await Promise.all([api('/admin/providers'), api('/admin/workspaces'), api('/admin/status')])
    setProviders(models.items); setWorkspaces(spaces.items); setStatus(health)
  }, [api])
  useEffect(() => { void load().catch(e => setError(e.message)) }, [load])
  async function save(action: () => Promise<unknown>) {
    setBusy(true); setError(''); setNotice('')
    try { await action(); await load(); setNotice('公用模型配置已保存') } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return <section className="admin-page">
    <div className="section-heading"><div><h1>管理后台</h1><p>查看运行状态，为工作区分配公用模型。</p></div><Button variant="quiet" onClick={() => void load().catch(e => setError(e.message))}>刷新状态</Button></div>
    {error && <Alert tone="danger">{error}</Alert>}{notice && <Alert tone="success">{notice}</Alert>}
    {status && <div className="admin-stats">{[['版本', status.version], ['用户', status.users], ['论文', status.papers], ['排队任务', status.queued], ['运行任务', status.running]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value ?? '—'}</strong></div>)}</div>}
    <h2>公用模型</h2><p>模型密钥保存在服务端，选中的工作区可直接使用。</p>
    <div className="shared-models">{providers.map(provider => <article key={provider.id}><div className="section-heading"><h3>{provider.name}</h3><Badge tone={provider.enabled ? 'success' : 'warning'}>{provider.enabled ? '可用' : '已停用'}</Badge></div><p>{provider.models.join(' / ')}</p><small>{provider.base_url}</small><fieldset><legend>授权工作区</legend>{workspaces.map(space => <label className="fastui-field" key={space.id}><Checkbox checked={provider.workspace_ids.includes(space.id)} disabled={busy} onChange={e => { const workspace_ids = e.target.checked ? [...provider.workspace_ids, space.id] : provider.workspace_ids.filter((id: string) => id !== space.id); void save(() => api(`/admin/providers/${provider.id}`, 'PATCH', { workspace_ids })) }} />{space.name}</label>)}</fieldset><Button variant="quiet" disabled={busy} onClick={() => void save(() => api(`/admin/providers/${provider.id}`, 'PATCH', { enabled: !provider.enabled }))}>{provider.enabled ? '停用模型' : '启用模型'}</Button></article>)}</div>
    <details className="admin-create-provider"><summary>添加公用模型</summary><form className="admin-form" onSubmit={e => { e.preventDefault(); const form = e.currentTarget; const data = Object.fromEntries(new FormData(form)); void save(async () => { await api('/admin/providers', 'POST', { ...data, models: String(data.models).split(/[,，]/).map(v => v.trim()).filter(Boolean), workspace_ids: assigned }); form.reset(); setAssigned([]) }) }}>
      <label>名称<TextField name="name" required maxLength={120} /></label><label>API 地址<TextField name="base_url" type="url" placeholder="https://api.example.com/v1" required /></label><label>API 密钥<TextField name="api_key" type="password" autoComplete="off" required /></label><label>模型 ID（逗号分隔）<TextField name="models" required placeholder="model-one, model-two" /></label>
      <fieldset><legend>授权工作区</legend>{workspaces.map(space => <label className="fastui-field" key={space.id}><Checkbox checked={assigned.includes(space.id)} onChange={e => setAssigned(ids => e.target.checked ? [...ids, space.id] : ids.filter(id => id !== space.id))} />{space.name}</label>)}</fieldset><Button type="submit" loading={busy}>保存公用模型</Button>
    </form></details>
  </section>
}
