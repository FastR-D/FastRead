import { useEffect, useState, type ReactNode } from 'react'
import {
  ActivityRail,
  Avatar,
  Button,
  CardBody,
  Dialog,
  PanelHeader,
  Section,
  TabBar,
  Toolbar,
} from '@fastrd/ui-react'
import { BookOpen, LogOut, Moon, ShieldCheck, Sun, X, PanelLeft } from 'lucide-react'
import { colorMode } from './theme'
import { safeIdentityLabel } from './identity'

export type MainSection = 'library' | 'admin' | 'settings'

export function AppHeader({
  user,
  section,
  onSection,
  onAccount,
  onLogout,
}: {
  user: Record<string, any>
  section: MainSection
  onSection: (section: MainSection) => void
  onAccount: () => void
  onLogout: () => void
}) {
  const [dark, setDark] = useState(() => document.documentElement.dataset.fastuiTheme === 'dark')
  useEffect(() => colorMode.subscribe(state => setDark(state.resolved === 'dark')), [])
  const label = safeIdentityLabel(user.display_name || user.workspace?.name, 'FastRead 用户')
  const admin = user.is_admin || user.role === 'admin'
  const tabs = [
    { id: 'library', label: '论文库', controls: 'main-library' },
    ...(admin ? [{ id: 'admin', label: '管理', controls: 'main-admin' }] : []),
    { id: 'settings', label: '设置', controls: 'main-settings' },
  ]
  return (
    <Section role="banner" className="app-topbar min-w-0 shrink-0">
      <Toolbar label="应用导航" className="app-topbar-inner">
        <Button variant="quiet" onClick={() => onSection('library')} aria-label="FastRead 论文库">
          <span className="app-brand-icon">
            <BookOpen size={18} />
          </span>
          <strong className="app-wordmark">FastRead</strong>
        </Button>
        <TabBar
          className="app-main-navigation"
          label="主导航"
          tabs={tabs}
          activeId={section}
          onSelect={id => onSection(id as MainSection)}
        />
        <Toolbar label="账号操作" className="app-account-actions">
          <Button variant="quiet" onClick={onAccount} title={label} aria-label="账号设置">
            <Avatar name={label} size="sm" />
            <span className="app-account-name">{label}</span>
          </Button>
          {!user.public && (
            <Button variant="icon" onClick={onLogout} aria-label="退出登录" title="退出登录">
              <LogOut size={17} />
            </Button>
          )}

          <Button variant="quiet" onClick={onAccount} aria-label="CAS 认证">
            <ShieldCheck size={17} />
            <span className="sr-only">CAS 认证</span>
          </Button>
          <Button
            variant="icon"
            onClick={() => colorMode.setMode(dark ? 'light' : 'dark')}
            aria-label={dark ? '切换浅色模式' : '切换暗黑模式'}
            title={dark ? '切换浅色模式' : '切换暗黑模式'}
          >
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </Button>
        </Toolbar>
      </Toolbar>
    </Section>
  )
}

export function AppDialog({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}) {
  return (
    <Dialog open={open} onClose={onClose} label={title} size="lg">
      <PanelHeader className="app-dialog-heading flex items-center justify-between gap-3">
        <h2 className="fastui-heading m-0 text-base">{title}</h2>
        <Button variant="icon" onClick={onClose} aria-label={`关闭${title}`}>
          <X size={18} />
        </Button>
      </PanelHeader>
      <CardBody className="fastui-modal-body min-w-0">{children}</CardBody>
    </Dialog>
  )
}

// Delegate keyboard navigation, focus and selection to FastUI.
export function WorkspaceTabs({
  label,
  tabs,
  activeId,
  onSelect,
  equal = false,
}: {
  label: string
  tabs: { id: string; label: string; controls: string; icon?: ReactNode; disabled?: boolean }[]
  activeId: string
  onSelect: (id: string) => void
  equal?: boolean
}) {
  return (
    <TabBar
      className={`workspace-tabs min-w-0 ${equal ? 'workspace-tabs-equal' : ''}`}
      label={label}
      tabs={tabs}
      activeId={activeId}
      onSelect={onSelect}
    />
  )
}

export function WorkbenchSidebar({
  id,
  label,
  tools,
  children,
}: {
  id: string
  label: string
  tools: { label: string; icon: ReactNode; onClick: () => void; active?: boolean }[]
  children: ReactNode
}) {
  const [expanded, setExpanded] = useState(false)
  return (
    <Section
      role="complementary"
      id={id}
      className={`workbench-sidebar ${expanded ? 'sidebar-expanded' : ''}`}
    >
      <PanelHeader className="sidebar-heading">
        <Button
          className="sidebar-mobile-toggle"
          variant="icon"
          aria-label={expanded ? '收起导航' : '展开导航'}
          aria-expanded={expanded}
          aria-controls={`${id}-body`}
          onClick={() => setExpanded(!expanded)}
        >
          <PanelLeft size={18} />
        </Button>
      </PanelHeader>
      <div id={`${id}-body`} className="sidebar-body">
        <ActivityRail label={label} className="sidebar-navigation">
          {tools.map(tool => (
            <Button
              key={tool.label}
              variant="navigation"
              aria-label={tool.label}
              title={tool.label}
              aria-pressed={tool.active}
              onClick={tool.onClick}
            >
              {tool.icon}
              <span>{tool.label === '资料库概览' ? '全部论文' : tool.label}</span>
            </Button>
          ))}
        </ActivityRail>
        <CardBody className="sidebar-content">{children}</CardBody>
      </div>
    </Section>
  )
}
