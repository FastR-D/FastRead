import {
  Alert,
  Badge,
  Button,
  Checkbox,
  EmptyState,
  ListRow,
  Loading,
  Section,
  Select,
  TextField,
} from '@fastrd/ui-react'
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  Building2,
  ChevronLeft,
  ChevronRight,
  KeyRound,
  Pencil,
  Plus,
  Power,
  RefreshCw,
  ShieldCheck,
  UserRound,
  Users,
} from 'lucide-react'
import { AppDialog } from './Chrome'

type Row = Record<string, any>
type Api = (path: string, method?: string, body?: unknown) => Promise<any>
type User = {
  id: string
  email: string
  display_name?: string
  role: string
  disabled: boolean
  created?: number
  workspace_names: string[]
}
type Provider = {
  id: string
  name: string
  base_url: string
  models: string[]
  enabled: boolean
  workspace_ids: string[]
  user_ids: string[]
}
type Workspace = { id: string; name: string }
type Grants = { workspace_ids: string[]; user_ids: string[] }
const pageSize = 20
const secondary = 'text-[var(--fastui-secondary)]'

// Membership rows belong to a single account in both user and grant lists.
function uniqueUsers(rows: Row[]): User[] {
  const users = new Map<string, User>()
  for (const row of rows) {
    const name = row.workspace_name || row.workspace_id
    const existing = users.get(row.id)
    if (existing) {
      if (name && !existing.workspace_names.includes(name)) existing.workspace_names.push(name)
    } else users.set(row.id, { ...row, workspace_names: name ? [name] : [] } as User)
  }
  return [...users.values()]
}
function PageHeading({ title, children }: { title: string; children: ReactNode }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4">
      <h1 className="fastui-heading m-0 text-2xl">{title}</h1>
      <div className="flex items-center gap-2">{children}</div>
    </header>
  )
}
function AdminTable({
  label,
  columns,
  children,
}: {
  label: string
  columns: string[]
  children: ReactNode
}) {
  return (
    <Section>
      <div className="fastui-table-scroll" role="region" aria-label={label} tabIndex={0}>
        <table className="fastui-table w-full min-w-[48rem]">
          <thead>
            <tr>
              {columns.map(column => (
                <th key={column} className="sticky top-0 whitespace-nowrap">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>{children}</tbody>
        </table>
      </div>
    </Section>
  )
}
function ListFooter({
  count,
  page,
  onPage,
  unit,
}: {
  count: number
  page: number
  onPage: (page: number) => void
  unit: string
}) {
  const pages = Math.max(1, Math.ceil(count / pageSize))
  return (
    <div className={`flex flex-wrap items-center justify-between gap-3 ${secondary}`}>
      <span>
        {count} {unit}
      </span>
      {pages > 1 && (
        <nav className="flex items-center gap-3" aria-label={`${unit}分页`}>
          <Button
            variant="quiet"
            aria-label="上一页"
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
          >
            <ChevronLeft size={15} />
          </Button>
          <span>
            {page} / {pages}
          </span>
          <Button
            variant="quiet"
            aria-label="下一页"
            disabled={page >= pages}
            onClick={() => onPage(page + 1)}
          >
            <ChevronRight size={15} />
          </Button>
        </nav>
      )}
    </div>
  )
}
function Identity({ user, current }: { user: User; current?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <UserRound size={18} className={`shrink-0 ${secondary}`} />
      <div className="grid min-w-0 gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <strong>{user.display_name || user.email}</strong>
          {current && <span className={`text-xs ${secondary}`}>当前账号</span>}
        </div>
        {user.display_name && user.display_name !== user.email && (
          <span className={`text-xs ${secondary}`}>{user.email}</span>
        )}
      </div>
    </div>
  )
}

export function UserManagement({ api, currentUser }: { api: Api; currentUser: Row }) {
  const [users, setUsers] = useState<User[]>([])
  const [query, setQuery] = useState(''),
    [role, setRole] = useState(''),
    [status, setStatus] = useState('')
  const [page, setPage] = useState(1),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState('')
  const [error, setError] = useState(''),
    [notice, setNotice] = useState('')
  const [dialog, setDialog] = useState<{ user?: User } | null>(null)
  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setUsers(uniqueUsers((await api('/admin/users')).items))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [api])
  useEffect(() => {
    void load()
  }, [load])
  const visible = users.filter(
    user =>
      (!role || user.role === role) &&
      (!status || (status === 'disabled') === user.disabled) &&
      `${user.display_name || ''} ${user.email} ${user.workspace_names.join(' ')}`
        .toLowerCase()
        .includes(query.trim().toLowerCase())
  )
  const currentPage = Math.min(page, Math.max(1, Math.ceil(visible.length / pageSize)))
  async function toggle(user: User) {
    setBusy(user.id)
    setError('')
    setNotice('')
    try {
      await api(`/admin/users/${user.id}`, 'PATCH', {
        disabled: !user.disabled,
        reason: user.disabled ? '管理员从用户列表启用账号' : '管理员从用户列表停用账号',
      })
      await load()
      setNotice(user.disabled ? '用户已启用' : '用户已停用')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }
  return (
    <section
      className="admin-page mx-auto box-border grid w-full max-w-7xl content-start gap-6 p-5 sm:p-8"
      aria-label="用户管理"
    >
      <PageHeading title="用户管理">
        <Button variant="primary" onClick={() => setDialog({})}>
          <Plus size={15} />
          新增用户
        </Button>
      </PageHeading>
      <div className="flex flex-wrap items-center gap-3">
        <TextField
          type="search"
          className="w-full sm:max-w-sm"
          aria-label="搜索用户"
          placeholder="搜索名称、邮箱或工作区"
          value={query}
          onChange={e => {
            setQuery(e.target.value)
            setPage(1)
          }}
        />
        <Select
          aria-label="筛选角色"
          value={role}
          onChange={e => {
            setRole(e.target.value)
            setPage(1)
          }}
        >
          <option value="">全部角色</option>
          <option value="user">普通用户</option>
          <option value="admin">系统管理员</option>
        </Select>
        <Select
          aria-label="筛选账号状态"
          value={status}
          onChange={e => {
            setStatus(e.target.value)
            setPage(1)
          }}
        >
          <option value="">全部状态</option>
          <option value="active">正常</option>
          <option value="disabled">已停用</option>
        </Select>
        <Button
          variant="quiet"
          className="sm:ml-auto"
          loading={loading}
          onClick={() => void load()}
        >
          <RefreshCw size={15} />
          刷新
        </Button>
      </div>
      {error && <Alert tone="danger">{error}</Alert>}
      {notice && <Alert tone="success">{notice}</Alert>}
      {loading && !users.length ? (
        <Loading label="正在加载用户…" />
      ) : (
        <>
          <AdminTable
            label="用户列表"
            columns={['用户', '工作区', '角色', '状态', '创建时间', '操作']}
          >
            {visible.slice((currentPage - 1) * pageSize, currentPage * pageSize).map(user => (
              <tr key={user.id} className="hover:bg-[var(--fastui-hover)]">
                <td>
                  <Identity user={user} current={user.id === currentUser.id} />
                </td>
                <td>
                  <span className="block max-w-52 truncate" title={user.workspace_names.join('、')}>
                    {user.workspace_names.join('、') || '—'}
                  </span>
                </td>
                <td>{user.role === 'admin' ? '系统管理员' : '普通用户'}</td>
                <td>
                  <Badge tone={user.disabled ? 'warning' : 'success'}>
                    {user.disabled ? '已停用' : '正常'}
                  </Badge>
                </td>
                <td className={`whitespace-nowrap ${secondary}`}>
                  {user.created ? new Date(user.created * 1000).toLocaleDateString('zh-CN') : '—'}
                </td>
                <td>
                  <div className="flex items-center gap-2 whitespace-nowrap">
                    <Button
                      variant="secondary"
                      disabled={!!busy || user.id === currentUser.id}
                      onClick={() => setDialog({ user })}
                    >
                      <Pencil size={14} />
                      编辑
                    </Button>
                    <Button
                      variant={user.disabled ? 'primary' : 'danger'}
                      loading={busy === user.id}
                      disabled={!!busy || user.id === currentUser.id}
                      onClick={() => void toggle(user)}
                    >
                      <Power size={14} />
                      {user.disabled ? '启用' : '停用'}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </AdminTable>
          {!visible.length && (
            <EmptyState title={query || role || status ? '没有匹配的用户' : '暂无用户'} />
          )}
          <ListFooter count={visible.length} page={currentPage} onPage={setPage} unit="位用户" />
        </>
      )}
      {dialog && (
        <UserDialog
          key={dialog.user?.id || 'new'}
          api={api}
          user={dialog.user}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null)
            setNotice(dialog.user ? '用户权限已更新' : '用户已创建')
            void load()
          }}
        />
      )}
    </section>
  )
}
function UserDialog({
  api,
  user,
  onClose,
  onSaved,
}: {
  api: Api
  user?: User
  onClose: () => void
  onSaved: () => void
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const [removing, setRemoving] = useState(false)
  return (
    <AppDialog
      open
      onClose={() => {
        if (!busy) onClose()
      }}
      title={user ? '编辑用户权限' : '新增用户'}
    >
      <form
        className="grid gap-5"
        onSubmit={e => {
          e.preventDefault()
          const data = Object.fromEntries(new FormData(e.currentTarget))
          setBusy(true)
          setError('')
          void (async () => {
            try {
              if (user) await api(`/admin/users/${user.id}`, removing ? 'DELETE' : 'PATCH', data)
              else await api('/admin/users', 'POST', data)
              onSaved()
            } catch (e) {
              setError((e as Error).message)
            } finally {
              setBusy(false)
            }
          })()
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="fastui-field">
            显示名称
            <TextField
              name="display_name"
              autoFocus
              maxLength={120}
              defaultValue={user?.display_name || ''}
              required
            />
          </label>
          <label className="fastui-field">
            邮箱
            <TextField
              name="email"
              type="email"
              autoComplete="off"
              defaultValue={user?.email || ''}
              required
            />
          </label>
          <label className="fastui-field">
            {user ? '重置密码（留空保持）' : '初始密码'}
            <TextField
              name="password"
              type="password"
              minLength={12}
              maxLength={256}
              autoComplete="new-password"
              required={!user}
            />
          </label>
          {!user && (
            <label className="fastui-field">
              工作区名称
              <TextField name="workspace_name" maxLength={120} required />
            </label>
          )}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="fastui-field">
            角色
            <Select aria-label="角色" name="role" defaultValue={user?.role || 'user'}>
              <option value="user">普通用户</option>
              <option value="admin">系统管理员</option>
            </Select>
          </label>
          {user && (
            <label className="fastui-field">
              账号状态
              <Select
                aria-label="账号状态"
                name="status"
                defaultValue={user.disabled ? 'disabled' : 'active'}
              >
                <option value="active">正常</option>
                <option value="disabled">已停用</option>
              </Select>
            </label>
          )}
        </div>
        <label className="fastui-field">
          操作原因
          <TextField name="reason" required maxLength={500} />
        </label>
        {removing && (
          <Alert tone="warning">确认删除 {user?.email}？账号将无法登录，工作区和资料保留。</Alert>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="flex justify-end gap-2">
          {user && (
            <Button
              className="mr-auto"
              variant="quiet"
              disabled={busy}
              onClick={() => setRemoving(!removing)}
            >
              {removing ? '取消删除' : '删除用户'}
            </Button>
          )}
          <Button variant="quiet" disabled={busy} onClick={onClose}>
            取消
          </Button>
          <Button variant={removing ? 'danger' : 'primary'} type="submit" loading={busy}>
            {removing ? '确认删除' : user ? '保存修改' : '创建用户'}
          </Button>
        </div>
      </form>
    </AppDialog>
  )
}

export function Administration({ api }: { api: Api }) {
  const [providers, setProviders] = useState<Provider[]>([]),
    [workspaces, setWorkspaces] = useState<Workspace[]>([]),
    [users, setUsers] = useState<User[]>([])
  const [status, setStatus] = useState<Row | null>(null),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState('')
  const [query, setQuery] = useState(''),
    [filter, setFilter] = useState(''),
    [page, setPage] = useState(1)
  const [error, setError] = useState(''),
    [notice, setNotice] = useState('')
  const [dialog, setDialog] = useState<{ provider?: Provider } | null>(null)
  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [models, spaces, accounts, health] = await Promise.all([
        api('/admin/providers'),
        api('/admin/workspaces'),
        api('/admin/users'),
        api('/admin/status'),
      ])
      setProviders(
        models.items.map((p: Provider) => ({
          ...p,
          workspace_ids: p.workspace_ids || [],
          user_ids: p.user_ids || [],
        }))
      )
      setWorkspaces(spaces.items)
      setUsers(uniqueUsers(accounts.items))
      setStatus(health)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [api])
  useEffect(() => {
    void load()
  }, [load])
  const visible = providers.filter(
    provider =>
      (!filter || (filter === 'enabled') === provider.enabled) &&
      `${provider.name} ${provider.base_url} ${provider.models.join(' ')}`
        .toLowerCase()
        .includes(query.trim().toLowerCase())
  )
  const currentPage = Math.min(page, Math.max(1, Math.ceil(visible.length / pageSize)))
  async function toggle(provider: Provider) {
    setBusy(provider.id)
    setError('')
    setNotice('')
    try {
      await api(`/admin/providers/${provider.id}`, 'PATCH', { enabled: !provider.enabled })
      await load()
      setNotice(provider.enabled ? '模型已停用' : '模型已启用')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }
  return (
    <section
      className="admin-page mx-auto box-border grid w-full max-w-7xl content-start gap-6 p-5 sm:p-8"
      aria-label="管理后台"
    >
      <PageHeading title="管理后台">
        <Button variant="primary" onClick={() => setDialog({})}>
          <Plus size={15} />
          添加公用模型
        </Button>
      </PageHeading>
      {status && (
        <Section className="grid grid-cols-2 sm:grid-cols-4">
          {[
            ['用户', status.users],
            ['论文', status.papers],
            ['排队中', status.queued],
            ['运行中', status.running],
          ].map(([name, value]) => (
            <div key={name} className="grid gap-2 p-5">
              <span className={secondary}>{name}</span>
              <strong className="text-xl">{value ?? '—'}</strong>
            </div>
          ))}
        </Section>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="fastui-heading m-0 mr-2 text-base">共享模型</h2>
        <TextField
          type="search"
          className="w-full sm:max-w-sm"
          aria-label="搜索模型"
          placeholder="搜索名称或模型 ID"
          value={query}
          onChange={e => {
            setQuery(e.target.value)
            setPage(1)
          }}
        />
        <Select
          aria-label="筛选模型状态"
          value={filter}
          onChange={e => {
            setFilter(e.target.value)
            setPage(1)
          }}
        >
          <option value="">全部状态</option>
          <option value="enabled">已启用</option>
          <option value="disabled">已停用</option>
        </Select>
        <Button
          variant="quiet"
          className="sm:ml-auto"
          loading={loading}
          onClick={() => void load()}
        >
          <RefreshCw size={15} />
          刷新状态
        </Button>
      </div>
      {error && <Alert tone="danger">{error}</Alert>}
      {notice && <Alert tone="success">{notice}</Alert>}
      {loading && !status ? (
        <Loading label="正在加载模型…" />
      ) : (
        <>
          <AdminTable label="共享模型列表" columns={['供应商', '模型', '授权范围', '状态', '操作']}>
            {visible.slice((currentPage - 1) * pageSize, currentPage * pageSize).map(provider => (
              <tr key={provider.id} className="hover:bg-[var(--fastui-hover)]">
                <td>
                  <div className="flex items-center gap-3">
                    <KeyRound size={18} className={`shrink-0 ${secondary}`} />
                    <div className="grid min-w-0 gap-1">
                      <strong>{provider.name}</strong>
                      <span
                        className={`block max-w-64 truncate text-xs ${secondary}`}
                        title={provider.base_url}
                      >
                        {provider.base_url}
                      </span>
                    </div>
                  </div>
                </td>
                <td>
                  <span className="block max-w-64 truncate" title={provider.models.join('、')}>
                    {provider.models.join('、')}
                  </span>
                </td>
                <td>
                  <div className={`flex flex-wrap items-center gap-3 ${secondary}`}>
                    {provider.workspace_ids.length || provider.user_ids.length ? (
                      <>
                        <span className="inline-flex items-center gap-1">
                          <Building2 size={14} />
                          {provider.workspace_ids.length} 工作区
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <Users size={14} />
                          {provider.user_ids.length} 用户
                        </span>
                      </>
                    ) : (
                      <span>未授权</span>
                    )}
                  </div>
                </td>
                <td>
                  <Badge tone={provider.enabled ? 'success' : 'warning'}>
                    {provider.enabled ? '已启用' : '已停用'}
                  </Badge>
                </td>
                <td>
                  <div className="flex items-center gap-1 whitespace-nowrap">
                    <Button
                      variant="quiet"
                      disabled={!!busy}
                      onClick={() => setDialog({ provider })}
                    >
                      <ShieldCheck size={14} />
                      授权
                    </Button>
                    <Button
                      variant="quiet"
                      loading={busy === provider.id}
                      disabled={!!busy}
                      onClick={() => void toggle(provider)}
                    >
                      <Power size={14} />
                      {provider.enabled ? '停用模型' : '启用模型'}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </AdminTable>
          {!visible.length && (
            <EmptyState title={query || filter ? '没有匹配的模型' : '暂无共享模型'} />
          )}
          <ListFooter count={visible.length} page={currentPage} onPage={setPage} unit="个供应商" />
        </>
      )}
      {status?.version && <span className={`text-xs ${secondary}`}>FastRead {status.version}</span>}
      {dialog && (
        <ProviderDialog
          key={dialog.provider?.id || 'new'}
          api={api}
          provider={dialog.provider}
          users={users}
          workspaces={workspaces}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null)
            setNotice(dialog.provider ? '授权已更新' : '模型已添加')
            void load()
          }}
        />
      )}
    </section>
  )
}

function ScopeList({
  label,
  icon,
  items,
  selected,
  onChange,
  disabled,
}: {
  label: string
  icon: ReactNode
  items: { id: string; label: string; detail?: string }[]
  selected: string[]
  onChange: (ids: string[]) => void
  disabled: boolean
}) {
  const [query, setQuery] = useState('')
  const visible = items.filter(item =>
    `${item.label} ${item.detail || ''}`.toLowerCase().includes(query.trim().toLowerCase())
  )
  const all = visible.length > 0 && visible.every(item => selected.includes(item.id))
  return (
    <fieldset className="fastui-fieldset m-0 min-w-0" disabled={disabled}>
      <legend className="fastui-legend">
        <span className="inline-flex items-center gap-2">
          {icon}
          {label}
          <span>{selected.length}</span>
        </span>
      </legend>
      <div className="flex min-w-0 flex-col gap-4">
        <TextField
          type="search"
          size="md"
          className="h-[max(var(--fastui-height-md),var(--fastui-touch-target))] w-full shrink-0"
          aria-label={`搜索${label}`}
          placeholder="搜索…"
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        <label className="fastui-field h-[max(var(--fastui-height-md),var(--fastui-touch-target))] shrink-0">
          <Checkbox
            checked={all}
            onChange={e => {
              const ids = new Set(selected)
              for (const item of visible) {
                if (e.target.checked) ids.add(item.id)
                else ids.delete(item.id)
              }
              onChange([...ids])
            }}
          />
          全选当前结果
        </label>
        <div
          className="flex max-h-64 shrink-0 flex-col overflow-auto"
          role="group"
          aria-label={label}
        >
          {visible.map(item => (
            <ListRow key={item.id} className="box-border h-16 shrink-0 py-2">
              <label className="fastui-field h-full min-w-0 w-full">
                <Checkbox
                  checked={selected.includes(item.id)}
                  onChange={e =>
                    onChange(
                      e.target.checked
                        ? [...selected, item.id]
                        : selected.filter(id => id !== item.id)
                    )
                  }
                />
                <span className="grid min-w-0 gap-1">
                  <span className="truncate" title={item.label}>
                    {item.label}
                  </span>
                  {item.detail && (
                    <span className={`truncate text-xs ${secondary}`} title={item.detail}>
                      {item.detail}
                    </span>
                  )}
                </span>
              </label>
            </ListRow>
          ))}
          {!visible.length && (
            <span className={`p-3 ${secondary}`}>{query ? '无匹配结果' : '暂无记录'}</span>
          )}
        </div>
      </div>
    </fieldset>
  )
}
function GrantPicker({
  users,
  workspaces,
  value,
  onChange,
  disabled,
}: {
  users: User[]
  workspaces: Workspace[]
  value: Grants
  onChange: (value: Grants) => void
  disabled: boolean
}) {
  return (
    <div className="grid items-start gap-4 sm:grid-cols-2">
      <ScopeList
        label="授权工作区"
        icon={<Building2 size={15} />}
        items={workspaces.map(w => ({ id: w.id, label: w.name }))}
        selected={value.workspace_ids}
        onChange={ids => onChange({ ...value, workspace_ids: ids })}
        disabled={disabled}
      />
      <ScopeList
        label="授权用户"
        icon={<Users size={15} />}
        items={users.map(u => ({
          id: u.id,
          label: u.display_name || u.email,
          detail: u.display_name ? u.email : undefined,
        }))}
        selected={value.user_ids}
        onChange={ids => onChange({ ...value, user_ids: ids })}
        disabled={disabled}
      />
    </div>
  )
}
function ProviderDialog({
  api,
  provider,
  users,
  workspaces,
  onClose,
  onSaved,
}: {
  api: Api
  provider?: Provider
  users: User[]
  workspaces: Workspace[]
  onClose: () => void
  onSaved: () => void
}) {
  const [grants, setGrants] = useState<Grants>({
    workspace_ids: [...(provider?.workspace_ids || [])],
    user_ids: [...(provider?.user_ids || [])],
  })
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  return (
    <AppDialog
      open
      onClose={() => {
        if (!busy) onClose()
      }}
      title={provider ? '模型授权' : '添加公用模型'}
    >
      <form
        className="grid gap-5"
        onSubmit={e => {
          e.preventDefault()
          const data = Object.fromEntries(new FormData(e.currentTarget))
          setBusy(true)
          setError('')
          void (async () => {
            try {
              if (provider) await api(`/admin/providers/${provider.id}`, 'PATCH', grants)
              else
                await api('/admin/providers', 'POST', {
                  ...data,
                  models: String(data.models)
                    .split(/[,，\n]/)
                    .map(m => m.trim())
                    .filter(Boolean),
                  ...grants,
                })
              onSaved()
            } catch (e) {
              setError((e as Error).message)
            } finally {
              setBusy(false)
            }
          })()
        }}
      >
        {provider ? (
          <strong className="text-base">{provider.name}</strong>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="fastui-field">
              名称
              <TextField name="name" autoFocus maxLength={120} required />
            </label>
            <label className="fastui-field">
              API 地址
              <TextField
                name="base_url"
                type="url"
                placeholder="https://api.example.com/v1"
                required
              />
            </label>
            <label className="fastui-field">
              API 密钥
              <TextField name="api_key" type="password" autoComplete="off" required />
            </label>
            <label className="fastui-field">
              模型 ID（逗号分隔）
              <TextField name="models" placeholder="model-a, model-b" required />
            </label>
          </div>
        )}
        <p className={`m-0 ${secondary}`}>
          工作区授权覆盖全部成员；用户授权仅对本人有效，任一匹配即可使用。
        </p>
        <GrantPicker
          users={users}
          workspaces={workspaces}
          value={grants}
          onChange={setGrants}
          disabled={busy}
        />
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="flex justify-end gap-2">
          <Button variant="quiet" disabled={busy} onClick={onClose}>
            取消
          </Button>
          <Button variant="primary" type="submit" loading={busy}>
            {provider ? '保存授权' : '保存公用模型'}
          </Button>
        </div>
      </form>
    </AppDialog>
  )
}
