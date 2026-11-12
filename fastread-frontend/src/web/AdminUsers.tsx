import { useEffect, useState } from 'react'
import { Alert, Button, Select, TextField } from '@fastrd/ui-react'

type User = { id: string; email: string; display_name: string; role: string; status: string }
type API = (path: string, method?: string, body?: unknown) => Promise<any>
const blank = { id: '', email: '', display_name: '', role: 'user', status: 'active', password: '', reason: '' }
export default function AdminUsers({ api, currentId }: { api: API; currentId: string }) {
  const [users, setUsers] = useState<User[]>([]), [form, setForm] = useState(blank), [query, setQuery] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false), [deleting, setDeleting] = useState(false)
  const load = async () => setUsers((await api('/admin/users')).items)
  useEffect(() => { void load().catch(e => setError(e.message)) }, [])
  async function save(remove = false) {
    setBusy(true); setError('')
    try { await api(`/admin/users${form.id ? `/${form.id}` : ''}`, remove ? 'DELETE' : form.id ? 'PATCH' : 'POST', form); setForm(blank); setDeleting(false); await load() }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return <section className="fastread-settings" aria-label="用户管理">
    <h2>用户管理</h2>{error && <Alert tone="danger">{error}</Alert>}
    <label>搜索用户<TextField value={query} onChange={e => setQuery(e.target.value)} /></label>
    <Button onClick={() => { setForm(blank); setDeleting(false) }}>创建用户</Button>
    <div style={{ overflowX: 'auto' }}><table className="admin-table"><thead><tr><th>姓名</th><th>邮箱</th><th>角色</th><th>状态</th><th>操作</th></tr></thead><tbody>
      {users.filter(u => `${u.email} ${u.display_name}`.toLowerCase().includes(query.toLowerCase())).map(u => <tr key={u.id}><td>{u.display_name || u.email}</td><td>{u.email}</td><td>{u.role === 'admin' ? '管理员' : '用户'}</td><td>{u.status === 'active' ? '启用' : '停用'}</td><td><Button onClick={() => { setForm({ ...u, password: '', reason: '' }); setDeleting(false) }}>编辑</Button></td></tr>)}
    </tbody></table></div>
    <form onSubmit={e => { e.preventDefault(); void save(deleting) }}>
      <h3>{form.id ? '编辑用户' : '创建用户'}</h3>
      <label>邮箱<TextField type="email" required value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} /></label>
      <label>姓名<TextField maxLength={120} value={form.display_name} onChange={e => setForm({ ...form, display_name: e.target.value })} /></label>
      <label>{form.id ? '重置密码（留空保持）' : '初始密码'}<TextField type="password" autoComplete="new-password" required={!form.id} minLength={12} maxLength={256} value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} /></label>
      <label>角色<Select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}><option value="user">用户</option><option value="admin">管理员</option></Select></label>
      <label>状态<Select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}><option value="active">启用</option><option value="disabled">停用</option></Select></label>
      <label>操作原因<TextField required value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} /></label>
      {deleting && <Alert tone="warning">确认删除 {form.email}？此账号将无法登录，现有会话会失效。</Alert>}
      <Button type="submit" loading={busy} variant={deleting ? 'danger' : 'primary'}>{deleting ? '确认删除' : '保存'}</Button>
      {form.id && form.id !== currentId && <Button type="button" disabled={busy} onClick={() => setDeleting(!deleting)}>{deleting ? '取消删除' : '删除用户'}</Button>}
    </form>
  </section>
}
