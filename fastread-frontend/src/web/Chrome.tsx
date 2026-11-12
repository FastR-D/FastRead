import { useEffect, useState, type ReactNode } from 'react'
import { Button, Dialog, TabBar } from '@fastrd/ui-react'
import { BookOpen, LogOut, Moon, Settings, ShieldCheck, Sun, X } from 'lucide-react'
import { colorMode } from './theme'
import { safeIdentityLabel } from './identity'

export type MainSection = 'library' | 'users' | 'admin'

export function AppHeader({ user, section, onSection, onSettings, onAccount, onLogout }: {
  user: Record<string, any>
  section: MainSection
  onSection: (section: MainSection) => void
  onSettings: () => void
  onAccount: () => void
  onLogout: () => void
}) {
  const [dark, setDark] = useState(() => document.documentElement.dataset.fastuiTheme === 'dark')
  useEffect(() => colorMode.subscribe(state => setDark(state.resolved === 'dark')), [])
  const label = safeIdentityLabel(user.display_name || user.workspace?.name, 'FastRead 用户')
  const admin = user.is_admin || user.role === 'admin'
  const tabs = [
    { id: 'library', label: '论文库', controls: 'main-library' },
    ...(admin ? [{ id: 'users', label: '用户管理', controls: 'main-users' }, { id: 'admin', label: '管理后台', controls: 'main-admin' }] : []),
  ]
  return <header className="app-header">
    <Button variant="quiet" className="app-brand" onClick={() => onSection('library')} aria-label="FastRead 论文库"><BookOpen size={22} /><strong>FastRead</strong></Button>
    <TabBar tabs={tabs} activeId={section} label="主导航" onSelect={id => onSection(id as MainSection)} />
    <div className="header-actions">
      <Button variant="quiet" className="account-button" onClick={onAccount} title={label} aria-label="账号设置"><span className="account-avatar" aria-hidden="true">{label.slice(0, 1).toUpperCase()}</span><span className="account-name">{label}</span></Button>
      {!user.public && <Button variant="icon" className="circle-button" onClick={onLogout} aria-label="退出登录" title="退出登录"><LogOut size={17} /></Button>}
      <Button variant="quiet" onClick={onSettings} aria-label="设置"><Settings size={17} /><span className="action-label">设置</span></Button>
      <Button variant="quiet" onClick={onAccount} aria-label="CAS 认证"><ShieldCheck size={17} /><span className="action-label">CAS 认证</span></Button>
      <Button variant="icon" onClick={() => colorMode.setMode(dark ? 'light' : 'dark')} aria-label={dark ? '切换浅色模式' : '切换暗黑模式'} title={dark ? '切换浅色模式' : '切换暗黑模式'}>{dark ? <Sun size={18} /> : <Moon size={18} />}</Button>
    </div>
  </header>
}

export function AppDialog({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  return <Dialog open={open} onClose={onClose} label={title} size="lg">
    <div className="app-dialog-heading"><h2>{title}</h2><Button variant="icon" onClick={onClose} aria-label={`关闭${title}`}><X size={18} /></Button></div>
    <div className="fastui-modal-body app-dialog-body">{children}</div>
  </Dialog>
}
