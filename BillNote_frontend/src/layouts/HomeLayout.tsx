import React, { FC } from 'react'
import {
  BookOpenText,
  Boxes,
  BrainCircuit,
  ChevronsRight,
  FileText,
  Library,
  MessageSquareText,
  PanelLeft,
  PanelRight,
  Plus,
  ScrollText,
  Settings,
  Sparkles,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
import { useTaskStore } from '@/store/taskStore'
import logo from '@/assets/icon.svg'

interface IProps {
  NoteForm: React.ReactNode
  Preview: React.ReactNode
  History: React.ReactNode
}

type WorkspaceViewMode = 'preview' | 'map' | 'cards'
type ChatMode = false | 'half' | 'full'

function emitWorkspaceCommand(command: {
  viewMode?: WorkspaceViewMode
  chat?: ChatMode
  transcribe?: boolean | 'toggle'
  action?: 'copy' | 'download'
}) {
  window.dispatchEvent(new CustomEvent('reelmind:workspace-command', { detail: command }))
}

function formatDate(value?: string) {
  if (!value) return '尚未创建'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '尚未创建'
  return date
    .toLocaleDateString('zh-CN', {
      month: 'long',
      day: 'numeric',
    })
    .replace(/\s/g, '')
}

const featureCards = [
  {
    title: '阅读笔记',
    desc: '查看结构化 Markdown',
    icon: BookOpenText,
    tone: 'border-sky-200 bg-sky-50 text-sky-800',
    command: { viewMode: 'preview' as const, chat: false as const },
  },
  {
    title: 'AI 对话',
    desc: '围绕当前视频追问',
    icon: MessageSquareText,
    tone: 'border-violet-200 bg-violet-50 text-violet-800',
    command: { viewMode: 'preview' as const, chat: 'half' as const },
  },
  {
    title: '思维导图',
    desc: '展开知识层级',
    icon: BrainCircuit,
    tone: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    command: { viewMode: 'map' as const, chat: false as const },
  },
  {
    title: '知识卡片',
    desc: '抽取结论与行动项',
    icon: Boxes,
    tone: 'border-amber-200 bg-amber-50 text-amber-900',
    command: { viewMode: 'cards' as const, chat: false as const },
  },
]

const utilityCards = [
  {
    title: '原文参照',
    desc: '打开转写文本',
    icon: ScrollText,
    command: { viewMode: 'preview' as const, transcribe: 'toggle' as const },
  },
  {
    title: '导出 Markdown',
    desc: '保存当前版本',
    icon: FileText,
    command: { action: 'download' as const },
  },
]

const HomeLayout: FC<IProps> = ({ NoteForm, Preview, History }) => {
  const currentTask = useTaskStore(state => state.getCurrentTask())

  return (
    <div className="h-screen overflow-hidden bg-[#f6f7f4] text-slate-900">
      <div className="grid h-full grid-cols-[336px_minmax(0,1fr)_316px] gap-px bg-slate-200/80">
        <aside className="flex min-h-0 flex-col bg-[#fbfbf8]">
          <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 px-5">
            <Link to="/" className="flex items-center gap-3">
              <img src={logo} alt="ReelMind" className="h-9 w-9 rounded-md" />
              <div>
                <div className="text-xl font-semibold leading-tight tracking-normal">ReelMind</div>
                <div className="text-xs text-slate-500">视频来源</div>
              </div>
            </Link>
            <Link
              to="/settings"
              className="inline-flex h-9 w-9 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
              title="设置"
            >
              <Settings className="h-4 w-4" />
            </Link>
          </header>

          <div className="border-b border-slate-200 px-5 py-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-700">
              <PanelLeft className="h-4 w-4 text-primary" />
              添加视频链接
            </div>
            <p className="text-xs leading-5 text-slate-500">
              粘贴抖音精选链接，生成后会进入中间工作区，并同步到主页笔记本库。
            </p>
          </div>

          <ScrollArea className="min-h-0 flex-1">
            <div className="px-4 py-4">{NoteForm}</div>
          </ScrollArea>
        </aside>

        <main className="flex min-h-0 flex-col bg-white">
          <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 px-6">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.16em] text-slate-400">
                <Sparkles className="h-3.5 w-3.5" />
                Workspace
              </div>
              <h1 className="mt-1 truncate text-lg font-semibold tracking-normal">
                {currentTask?.audioMeta?.title || '新视频笔记'}
              </h1>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => emitWorkspaceCommand({ viewMode: 'preview', chat: false })}
                className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
              >
                <BookOpenText className="h-4 w-4" />
                笔记
              </button>
              <button
                type="button"
                onClick={() => emitWorkspaceCommand({ viewMode: 'preview', chat: 'full' })}
                className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-md bg-slate-950 px-3 text-sm font-medium text-white transition hover:bg-slate-800"
              >
                <MessageSquareText className="h-4 w-4" />
                对话
              </button>
            </div>
          </header>
          <section className="min-h-0 flex-1 overflow-hidden bg-white">{Preview}</section>
        </main>

        <aside className="flex min-h-0 flex-col bg-[#fbfbf8]">
          <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 px-5">
            <div>
              <div className="text-base font-semibold">功能卡片</div>
              <div className="text-xs text-slate-500">{formatDate(currentTask?.createdAt)} · 当前笔记</div>
            </div>
            <PanelRight className="h-4 w-4 text-slate-400" />
          </header>

          <ScrollArea className="min-h-0 flex-1">
            <div className="space-y-6 p-4">
              <section>
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-slate-800">工作模式</h2>
                  <span className="text-xs text-slate-400">切换中间区</span>
                </div>
                <div className="grid gap-3">
                  {featureCards.map(card => {
                    const Icon = card.icon
                    return (
                      <button
                        key={card.title}
                        type="button"
                        onClick={() => emitWorkspaceCommand(card.command)}
                        className={`group flex min-h-20 cursor-pointer items-center gap-3 rounded-lg border px-3 py-3 text-left transition hover:-translate-y-0.5 hover:shadow-sm ${card.tone}`}
                      >
                        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-white/80">
                          <Icon className="h-5 w-5" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-semibold">{card.title}</span>
                          <span className="mt-1 block truncate text-xs opacity-75">{card.desc}</span>
                        </span>
                        <ChevronsRight className="h-4 w-4 shrink-0 opacity-50 transition group-hover:translate-x-0.5 group-hover:opacity-90" />
                      </button>
                    )
                  })}
                </div>
              </section>

              <section>
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-slate-800">辅助操作</h2>
                  <button
                    type="button"
                    onClick={() => emitWorkspaceCommand({ action: 'copy' })}
                    className="cursor-pointer text-xs font-medium text-primary hover:text-primary/80"
                  >
                    复制
                  </button>
                </div>
                <div className="grid gap-2">
                  {utilityCards.map(card => {
                    const Icon = card.icon
                    return (
                      <button
                        key={card.title}
                        type="button"
                        onClick={() => emitWorkspaceCommand(card.command)}
                        className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-3 text-left transition hover:border-slate-300 hover:bg-slate-50"
                      >
                        <Icon className="h-4 w-4 text-slate-600" />
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-medium text-slate-800">{card.title}</span>
                          <span className="block truncate text-xs text-slate-500">{card.desc}</span>
                        </span>
                      </button>
                    )
                  })}
                </div>
              </section>

              <section className="rounded-lg border border-slate-200 bg-white">
                <div className="flex items-center justify-between border-b border-slate-100 px-3 py-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                    <Library className="h-4 w-4 text-slate-500" />
                    最近笔记
                  </div>
                  <Link to="/" className="inline-flex items-center gap-1 text-xs font-medium text-primary">
                    主页
                    <ChevronsRight className="h-3.5 w-3.5" />
                  </Link>
                </div>
                <div className="max-h-[280px] overflow-hidden px-2 py-2">{History}</div>
              </section>

              <button
                type="button"
                onClick={() => useTaskStore.getState().setCurrentTask(null)}
                className="flex h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-lg bg-slate-950 text-sm font-semibold text-white transition hover:bg-slate-800"
              >
                <Plus className="h-4 w-4" />
                新视频笔记
              </button>
            </div>
          </ScrollArea>
        </aside>
      </div>
    </div>
  )
}

export default HomeLayout
