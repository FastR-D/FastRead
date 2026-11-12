import { useEffect, useState, type ReactNode } from 'react'
import { ActivityRail, Button, Dialog, Toolbar } from '@fastrd/ui-react'
import { BookOpen, LogOut, Moon, Settings, ShieldCheck, Sun, X } from 'lucide-react'
import { tabNavigationIndex } from '@fastrd/ui-foundation'
import { colorMode } from './theme'
import { safeIdentityLabel } from './identity'

export type MainSection = 'library' | 'users' | 'admin'

export function AppHeader({
  user,
  section,
  onSection,
  onSettings,
  onAccount,
  onLogout,
}: {
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
    ...(admin
      ? [
          { id: 'users', label: '用户管理', controls: 'main-users' },
          { id: 'admin', label: '管理后台', controls: 'main-admin' },
        ]
      : []),
  ]
  return (
    <header className="min-w-0 shrink-0">
      <Toolbar label="应用导航">
        <Button variant="quiet" onClick={() => onSection('library')} aria-label="FastRead 论文库">
          <BookOpen size={20} />
          <strong>FastRead</strong>
        </Button>
        <nav
          className="order-last flex w-full flex-wrap items-center gap-2 sm:order-none sm:w-auto"
          aria-label="主导航"
        >
          {tabs.map(tab => (
            <Button
              key={tab.id}
              id={tab.id}
              variant={section === tab.id ? 'primary' : 'quiet'}
              aria-current={section === tab.id ? 'page' : undefined}
              onClick={() => onSection(tab.id as MainSection)}
            >
              {tab.label}
            </Button>
          ))}
        </nav>
        <div className="flex min-w-0 flex-wrap items-center gap-1 sm:ml-auto">
          <Button variant="quiet" onClick={onAccount} title={label} aria-label="账号设置">
            <span className="max-w-24 truncate">{label}</span>
          </Button>
          {!user.public && (
            <Button variant="icon" onClick={onLogout} aria-label="退出登录" title="退出登录">
              <LogOut size={17} />
            </Button>
          )}
          <Button variant="quiet" onClick={onSettings} aria-label="设置">
            <Settings size={17} />
            <span className="hidden md:inline">设置</span>
          </Button>
          <Button variant="quiet" onClick={onAccount} aria-label="CAS 认证">
            <ShieldCheck size={17} />
            <span className="hidden md:inline">CAS 认证</span>
          </Button>
          <Button
            variant="icon"
            onClick={() => colorMode.setMode(dark ? 'light' : 'dark')}
            aria-label={dark ? '切换浅色模式' : '切换暗黑模式'}
            title={dark ? '切换浅色模式' : '切换暗黑模式'}
          >
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </Button>
        </div>
      </Toolbar>
    </header>
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
      <header className="flex items-center justify-between gap-3">
        <h2 className="fastui-heading m-0 text-base">{title}</h2>
        <Button variant="icon" onClick={onClose} aria-label={`关闭${title}`}>
          <X size={18} />
        </Button>
      </header>
      <div className="fastui-modal-body min-w-0">{children}</div>
    </Dialog>
  )
}

// Compose native FastUI tabs with icon labels and evenly spaced tool slots.
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
  const focusId =
    tabs.find(tab => tab.id === activeId && !tab.disabled)?.id ??
    tabs.find(tab => !tab.disabled)?.id
  return (
    <div
      className="fastui-tabs min-w-0 [--fastui-tab-height:42px]"
      role="tablist"
      aria-label={label}
    >
      {tabs.map((tab, index) => (
        <div key={tab.id} className={`fastui-tab-item ${equal ? '!flex-1' : ''}`}>
          <button
            className="fastui-tab w-full"
            type="button"
            role="tab"
            id={tab.id}
            aria-controls={tab.controls}
            aria-selected={activeId === tab.id}
            disabled={tab.disabled}
            tabIndex={focusId === tab.id ? 0 : -1}
            onClick={() => onSelect(tab.id)}
            onKeyDown={event => {
              if (event.nativeEvent.isComposing) return
              const next = tabNavigationIndex(
                event.key,
                index,
                tabs,
                getComputedStyle(event.currentTarget).direction === 'rtl'
              )
              if (next < 0) return
              event.preventDefault()
              onSelect(tabs[next].id)
              const buttons = event.currentTarget
                .closest('[role="tablist"]')
                ?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
              buttons?.[next]?.focus()
            }}
          >
            {tab.icon}
            <span className="fastui-tab-label">{tab.label}</span>
          </button>
        </div>
      ))}
    </div>
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
  return (
    <aside
      id={id}
      className="flex min-h-0 min-w-0 border-r border-[var(--fastui-border)] bg-[var(--fastui-chrome)]"
    >
      <ActivityRail label={label} className="shrink-0">
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
          </Button>
        ))}
      </ActivityRail>
      <div className="min-w-0 flex-1 lg:overflow-auto">{children}</div>
    </aside>
  )
}
