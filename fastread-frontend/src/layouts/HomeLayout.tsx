import type React from 'react'
import { type FC } from 'react'
import {
  BookOpenCheck,
  ChevronRight,
  FileInput,
  FileStack,
  FileText,
  Library,
  MessageSquareText,
  Plus,
  Search,
  Settings,
  Network,
  Sparkles,
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useTaskStore, type TaskStatus } from '@/store/taskStore'
import type { ReadingViewMode } from '@/pages/HomePage/components/WorkspacePanels'
import logo from '@/assets/icon.png'
import { emitWorkspaceCommand as dispatchWorkspaceCommand } from '@/utils/workspaceNavigation'

interface IProps {
  NoteForm: React.ReactNode
  Preview: React.ReactNode
}

function emitWorkspaceCommand(viewMode: ReadingViewMode, taskId?: string) {
  dispatchWorkspaceCommand({ taskId, viewMode, chat: viewMode === 'chat' ? 'full' : false })
}

const STATUS_META: Record<string, { label: string; tone: string; dot: string }> = {
  PENDING: { label: '排队中', tone: 'bg-slate-100 text-slate-600', dot: 'bg-slate-400' },
  PARSING_DOCUMENT: { label: '解析论文', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  GENERATING_REPORT: { label: '生成报告', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  FINDING_RELATED_WORK: { label: '查找近邻', tone: 'bg-violet-50 text-violet-700', dot: 'bg-violet-500' },
  WRITING_REPORT: { label: '写入报告', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  SUCCESS: { label: '原文已就绪', tone: 'bg-emerald-50 text-emerald-700', dot: 'bg-emerald-500' },
  FAILED: { label: '处理失败', tone: 'bg-red-50 text-red-700', dot: 'bg-red-500' },
}

function statusMeta(status?: TaskStatus | string) {
  return STATUS_META[status || 'PENDING'] || STATUS_META.PENDING
}

function relativeTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const minutes = Math.floor((Date.now() - date.getTime()) / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.floor(hours / 24)} 天前`
}

const FLOW = [
  { label: 'PDF / URL', caption: '导入论文', view: 'source' as const, icon: FileInput },
  { label: '分页原文', caption: '逐页可检索', view: 'source' as const, icon: FileText },
  { label: '关键问题', caption: '引导式报告', view: 'report' as const, icon: BookOpenCheck },
  { label: '方法与贡献', caption: '过程与增量', view: 'report' as const, icon: FileStack },
  { label: '近邻论文', caption: '相关工作', view: 'related' as const, icon: Network },
  { label: '300 字总结', caption: '自己的理解', view: 'summary' as const, icon: Sparkles },
  { label: '持续追问', caption: '回答带页码', view: 'chat' as const, icon: MessageSquareText },
]

const HomeLayout: FC<IProps> = ({ NoteForm, Preview }) => {
  const navigate = useNavigate()
  const currentTask = useTaskStore(state => state.getCurrentTask())
  const tasks = useTaskStore(state => state.tasks)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const paper = currentTask?.paperDocument
  const report = currentTask?.insights?.reading_report
  const summary = currentTask?.insights?.personal_summary
  const meta = statusMeta(currentTask?.status)
  const recentPapers = tasks
    .slice(0, 6)

  return (
    <div className="h-screen overflow-hidden bg-slate-100 text-slate-900">
      <div className="grid h-full grid-cols-1 grid-rows-[auto_minmax(0,1fr)] gap-px bg-slate-200 lg:grid-cols-[320px_minmax(0,1fr)] lg:grid-rows-1 xl:grid-cols-[340px_minmax(0,1fr)_300px]">
        <aside className="flex max-h-[46vh] min-h-0 flex-col bg-white lg:max-h-none">
          <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 px-4">
            <Link to="/" className="flex items-center gap-2.5">
              <img src={logo} alt="FastRead" className="h-7 w-7 rounded-sm" />
              <div className="leading-tight">
                <div className="text-[15px] font-semibold tracking-tight">FastRead</div>
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-400">
                  Paper Reading Workbench
                </div>
              </div>
            </Link>
            <div className="flex items-center gap-1">
              <Link to="/search" className="inline-flex h-8 w-8 items-center justify-center rounded-sm text-slate-400 transition hover:bg-emerald-50 hover:text-emerald-700" title="学术论文检索">
                <Search className="h-4 w-4" />
              </Link>
              <Link to="/research" className="inline-flex h-8 w-8 items-center justify-center rounded-sm text-slate-400 transition hover:bg-blue-50 hover:text-blue-700" title="专题知识库">
                <Network className="h-4 w-4" />
              </Link>
              <Link
                to="/settings"
                className="inline-flex h-8 w-8 items-center justify-center rounded-sm text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                title="设置"
              >
                <Settings className="h-4 w-4" />
              </Link>
            </div>
          </header>
          <div className="shrink-0 border-b border-slate-200 bg-slate-50/70 px-4 py-3">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-600">
              <FileInput className="h-3.5 w-3.5" />
              从论文开始
            </div>
            <p className="mt-1.5 text-xs leading-5 text-slate-500">
              PDF 或论文 URL 是主入口。近邻论文只做相关工作发现与来源展示。
            </p>
          </div>
          <ScrollArea className="min-h-0 flex-1">
            <div className="px-4 py-4">{NoteForm}</div>
          </ScrollArea>
        </aside>

        <main className="flex min-h-0 flex-col bg-white">
          <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-slate-200 px-5">
            <div className="min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">学术阅读任务</div>
              <h1 className="mt-0.5 truncate text-[15px] font-semibold tracking-tight text-slate-900">
                {currentTask?.title || '导入一篇论文开始阅读'}
              </h1>
            </div>
            {currentTask && (
              <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-sm px-2 py-0.5 text-[11px] font-medium ${meta.tone}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
                {meta.label}
              </span>
            )}
          </header>

          <nav aria-label="论文阅读流程" className="grid shrink-0 grid-cols-3 border-b border-slate-200 bg-white md:grid-cols-7">
            {FLOW.map((item, index) => {
              const Icon = item.icon
              const complete = Boolean(
                (index <= 1 && paper)
                || (index >= 2 && index <= 3 && report)
                || (index === 5 && summary?.content)
              )
              return (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => emitWorkspaceCommand(item.view)}
                  className="group flex min-w-0 items-center gap-2 border-r border-slate-100 px-3 py-2.5 text-left transition last:border-r-0 hover:bg-slate-50"
                >
                  <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                    complete ? 'bg-emerald-100 text-emerald-700' : index === 0 ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-500'
                  }`}>
                    {complete ? '✓' : <Icon className="h-3.5 w-3.5" />}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-[11px] font-semibold text-slate-800">{item.label}</span>
                    <span className="hidden truncate text-[9px] text-slate-400 xl:block">{item.caption}</span>
                  </span>
                </button>
              )
            })}
          </nav>

          <section className="min-h-0 flex-1 overflow-hidden bg-white">{Preview}</section>
        </main>

        <aside className="hidden min-h-0 flex-col bg-white xl:flex">
          <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 px-4">
            <div>
              <div className="text-[13px] font-semibold text-slate-800">论文进度</div>
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-400">Reading State</div>
            </div>
            <button
              type="button"
              onClick={() => {
                setCurrentTask(null)
                navigate('/workspace?view=source', { replace: true })
              }}
              className="inline-flex h-7 items-center gap-1 rounded-sm border border-slate-200 px-2 text-[11px] font-medium text-slate-600 hover:bg-slate-50"
            >
              <Plus className="h-3 w-3" /> 新论文
            </button>
          </header>

          <ScrollArea className="min-h-0 flex-1">
            <div className="space-y-5 p-4">
              <section>
                <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">当前论文</h2>
                {paper ? (
                  <dl className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white text-xs">
                    <MetaRow label="分页原文" value={`${paper.page_count || paper.pages.length} 页`} />
                    <MetaRow label="关键问题报告" value={report ? '已生成' : '待生成'} />
                    <MetaRow label="300 字总结" value={summary?.content ? `${summary.content.length} 字` : '待填写'} />
                    <MetaRow label="持续追问" value="页码优先" />
                  </dl>
                ) : (
                  <div className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-3 py-5 text-center text-xs text-slate-400">
                    导入论文后显示阅读进度
                  </div>
                )}
              </section>

              <section>
                <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">相关工作</h2>
                <button type="button" onClick={() => emitWorkspaceCommand('related')} className="flex w-full items-start gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-left transition hover:border-slate-300 hover:bg-white">
                  <Network className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
                  <span><span className="block text-xs font-semibold text-slate-700">查找近邻论文</span><span className="mt-1 block text-[11px] leading-4 text-slate-500">按报告锚点说明相近之处，不做真假裁决。</span></span>
                </button>
              </section>

              <section>
                <div className="mb-2 flex items-center gap-2">
                  <Library className="h-3.5 w-3.5 text-slate-400" />
                  <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">最近论文</h2>
                </div>
                {recentPapers.length ? (
                  <ul className="overflow-hidden divide-y divide-slate-100 rounded-md border border-slate-200">
                    {recentPapers.map(task => (
                      <li key={task.id} className="min-w-0 overflow-hidden">
                        <button
                          type="button"
                          onClick={() => emitWorkspaceCommand('source', task.id)}
                          className="flex w-full min-w-0 items-center gap-2 overflow-hidden px-3 py-2.5 text-left hover:bg-slate-50"
                        >
                          <FileText className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                          <span className="min-w-0 flex-1">
                            <span
                              className="line-clamp-2 break-words text-xs font-medium leading-4 text-slate-800"
                              title={task.title || '未命名论文'}
                            >
                              {task.title || '未命名论文'}
                            </span>
                            <span className="mt-0.5 block text-[10px] text-slate-400">{relativeTime(task.createdAt)}</span>
                          </span>
                          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-300" />
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="rounded-md border border-dashed border-slate-200 px-3 py-4 text-center text-xs text-slate-400">暂无论文</p>
                )}
              </section>
            </div>
          </ScrollArea>
        </aside>
      </div>
    </div>
  )
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-2.5">
      <dt className="text-[11px] text-slate-500">{label}</dt>
      <dd className="text-right text-xs font-medium text-slate-800">{value}</dd>
    </div>
  )
}

export default HomeLayout
