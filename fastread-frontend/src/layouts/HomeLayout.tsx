import React, { FC } from 'react'
import {
  BookOpenText,
  BookOpenCheck,
  ChevronRight,
  Copy,
  Download,
  FileText,
  MessageSquareText,
  Plus,
  SearchCheck,
  Settings,
  ShieldCheck,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
import { useTaskStore } from '@/store/taskStore'
import type { TaskStatus } from '@/store/taskStore'
import logo from '@/assets/icon.png'

interface IProps {
  NoteForm: React.ReactNode
  Preview: React.ReactNode
}

type WorkspaceViewMode = 'report' | 'verify' | 'preview' | 'map' | 'cards'
type ChatMode = false | 'half' | 'full'

function emitWorkspaceCommand(command: {
  viewMode?: WorkspaceViewMode
  chat?: ChatMode
  transcribe?: boolean | 'toggle'
  action?: 'copy' | 'download'
}) {
  window.dispatchEvent(new CustomEvent('fastread:workspace-command', { detail: command }))
}

const STATUS_META: Record<string, { label: string; tone: string; dot: string }> = {
  PENDING: { label: '排队中', tone: 'bg-slate-100 text-slate-600', dot: 'bg-slate-400' },
  PARSING: { label: '解析输入', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  DOWNLOADING: { label: '抓取原文', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  TRANSCRIBING: { label: '转写中', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  SUMMARIZING: { label: '摘要中', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  FORMATTING: { label: '排版中', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  SAVING: { label: '保存中', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  EXTRACTING_CLAIMS: { label: '提取主张', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  SEARCHING_WEB: { label: '联网检索', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  FETCHING_SOURCES: { label: '抓取信源', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  EVALUATING_EVIDENCE: { label: '评估证据', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  WRITING_REPORT: { label: '生成报告', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  RUNNING: { label: '运行中', tone: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  SUCCESS: { label: '已完成', tone: 'bg-emerald-50 text-emerald-700', dot: 'bg-emerald-500' },
  FAILED: { label: '失败', tone: 'bg-red-50 text-red-700', dot: 'bg-red-500' },
}

function statusMeta(status?: TaskStatus | string) {
  return STATUS_META[status || 'PENDING'] || STATUS_META.PENDING
}

function formatTimestamp(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function relativeTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const diff = Date.now() - date.getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小时前`
  const day = Math.floor(hr / 24)
  if (day < 30) return `${day} 天前`
  return formatTimestamp(value)
}

function shortId(id?: string) {
  if (!id) return '—'
  return id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id
}

const HomeLayout: FC<IProps> = ({ NoteForm, Preview }) => {
  const currentTask = useTaskStore(state => state.getCurrentTask())
  const tasks = useTaskStore(state => state.tasks)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)

  const status = currentTask?.status || 'PENDING'
  const meta = statusMeta(status)
  const verification = currentTask?.insights?.verification
  const counts = verification?.claim_counts
  const recentCases = tasks.slice(0, 6)
  const isActive = !['SUCCESS', 'FAILED', undefined].includes(status as any)

  return (
    <div className="h-screen overflow-hidden bg-slate-100 text-slate-900">
      <div className="grid h-full grid-cols-1 grid-rows-[auto_minmax(0,1fr)] gap-px bg-slate-200 lg:grid-cols-[320px_minmax(0,1fr)] lg:grid-rows-1 xl:grid-cols-[340px_minmax(0,1fr)_324px]">
        {/* ───────── 左侧：核实输入 ───────── */}
        <aside className="flex max-h-[46vh] min-h-0 flex-col bg-white lg:max-h-none">
          <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 px-4">
            <Link to="/" className="flex items-center gap-2.5">
              <img src={logo} alt="FastRead" className="h-7 w-7 rounded-sm" />
              <div className="leading-tight">
                <div className="text-[15px] font-semibold tracking-tight">FastRead</div>
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-400">
                  Academic Reading Workbench
                </div>
              </div>
            </Link>
            <Link
              to="/settings"
              className="inline-flex h-8 w-8 items-center justify-center rounded-sm text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              title="设置"
            >
              <Settings className="h-4 w-4" />
            </Link>
          </header>

          <div className="shrink-0 border-b border-slate-200 bg-slate-50/60 px-4 py-3">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              <SearchCheck className="h-3.5 w-3.5 text-slate-700" />
              论文输入
            </div>
            <p className="mt-1.5 text-xs leading-5 text-slate-500">
              导入论文 PDF，或粘贴论文 URL / 原文；先理解研究过程与贡献，再查看证据核验层。
            </p>
          </div>

          <ScrollArea className="min-h-0 flex-1">
            <div className="px-4 py-4">{NoteForm}</div>
          </ScrollArea>
        </aside>

        {/* ───────── 中间：核实工作区 ───────── */}
        <main className="flex min-h-0 flex-col bg-white">
          <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-slate-200 px-5">
            <div className="flex min-w-0 items-center gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  学术阅读
                </div>
                <h1 className="mt-0.5 truncate text-[15px] font-semibold tracking-tight text-slate-900">
                  {currentTask?.audioMeta?.title || currentTask?.formData?.video_url || '新核实会话'}
                </h1>
              </div>
              {currentTask && (
                <span
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-sm px-2 py-0.5 text-[11px] font-medium ${meta.tone}`}
                  title={status}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${meta.dot} ${isActive ? 'animate-pulse' : ''}`} />
                  {meta.label}
                </span>
              )}
            </div>

            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={() => emitWorkspaceCommand({ viewMode: 'report', chat: false })}
                className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-sm bg-slate-900 px-3 text-xs font-semibold text-white transition hover:bg-slate-700"
              >
                <BookOpenCheck className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">阅读报告</span>
              </button>
              <button
                type="button"
                onClick={() => emitWorkspaceCommand({ viewMode: 'verify', chat: false })}
                className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-sm px-2.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
              >
                <SearchCheck className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">核实报告</span>
              </button>
              <div className="mx-1 h-5 w-px bg-slate-200" />
              <button
                type="button"
                onClick={() => emitWorkspaceCommand({ viewMode: 'preview', chat: false })}
                className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-sm px-2.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
              >
                <BookOpenText className="h-3.5 w-3.5" />
                <span className="hidden xl:inline">Markdown</span>
              </button>
              <button
                type="button"
                onClick={() => emitWorkspaceCommand({ viewMode: 'report', chat: 'full' })}
                className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-sm px-2.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
              >
                <MessageSquareText className="h-3.5 w-3.5" />
                <span className="hidden xl:inline">对话</span>
              </button>
            </div>
          </header>
          <section className="min-h-0 flex-1 overflow-hidden bg-white">{Preview}</section>
        </main>

        {/* ───────── 右侧：核实会话 / 审计 ───────── */}
        <aside className="hidden min-h-0 flex-col bg-white xl:flex">
          <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 px-4">
            <div className="leading-tight">
              <div className="text-[13px] font-semibold tracking-tight text-slate-800">核实会话</div>
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-400">
                Case Audit
              </div>
            </div>
            <button
              type="button"
              onClick={() => setCurrentTask(null)}
              className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-sm border border-slate-200 px-2 text-[11px] font-medium text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900"
              title="清空当前会话并回到新核实"
            >
              <Plus className="h-3 w-3" />
              新建
            </button>
          </header>

          <ScrollArea className="min-h-0 flex-1">
            <div className="flex flex-col gap-4 p-4">
              {/* 当前会话元数据 */}
              <section>
                <div className="mb-2 flex items-center justify-between">
                  <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                    当前会话
                  </h2>
                  {currentTask && (
                    <span className={`inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[10px] font-medium ${meta.tone}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
                      {meta.label}
                    </span>
                  )}
                </div>

                {currentTask ? (
                  <dl className="divide-y divide-slate-100 rounded-sm border border-slate-200 bg-white text-xs">
                    <MetaRow label="会话 ID" value={<span className="font-mono text-[11px] text-slate-700">{shortId(currentTask.id)}</span>} />
                    <MetaRow label="创建时间" value={<span className="font-mono text-[11px] text-slate-700">{formatTimestamp(currentTask.createdAt)}</span>} />
                    <MetaRow label="输入类型" value={<span className="text-slate-700">{currentTask.formData?.input_mode === 'paper' ? '论文 PDF / URL' : currentTask.formData?.input_mode === 'url' ? '网页 URL' : '文本'}</span>} />
                    <MetaRow label="核验模型" value={<span className="truncate text-slate-700">{currentTask.formData?.model_name || '—'}</span>} />
                    <MetaRow label="核验深度" value={<span className="text-slate-700">{currentTask.formData?.verification_depth === 'deep' ? '深度' : '标准'}</span>} />
                    <MetaRow label="信源策略" value={<span className="text-slate-700">{currentTask.formData?.source_policy === 'authoritative' ? '权威优先' : '—'}</span>} />
                  </dl>
                ) : (
                  <div className="rounded-sm border border-dashed border-slate-200 bg-slate-50/60 px-3 py-4 text-center text-xs text-slate-400">
                    尚无活动会话
                  </div>
                )}
              </section>

              {/* 核实结论概览 */}
              {verification && (
                <section>
                  <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                    结论概览
                  </h2>
                  <div className="rounded-sm border border-slate-200 bg-white">
                    <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
                      <span className="text-[11px] text-slate-500">总体判定</span>
                      <span className="text-xs font-semibold text-slate-900">{verification.overall?.status || '—'}</span>
                    </div>
                    <div className="grid grid-cols-3 divide-x divide-slate-100">
                      <TallyCell label="主张" value={counts?.total ?? verification.claims.length} tone="text-slate-900" />
                      <TallyCell label="支持" value={counts?.online_supported ?? 0} tone="text-emerald-700" />
                      <TallyCell label="反证" value={counts?.online_refuted ?? 0} tone="text-red-700" />
                    </div>
                    <div className="grid grid-cols-2 divide-x divide-slate-100 border-t border-slate-100">
                      <TallyCell label="已联网" value={counts?.online_checked ?? 0} tone="text-slate-900" />
                      <TallyCell label="风险旗标" value={verification.risk_flags?.length ?? 0} tone="text-amber-700" />
                    </div>
                  </div>
                </section>
              )}

              {/* 最近会话 */}
              <section>
                <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                  最近会话
                </h2>
                {recentCases.length === 0 ? (
                  <div className="rounded-sm border border-dashed border-slate-200 bg-slate-50/60 px-3 py-4 text-center text-xs text-slate-400">
                    暂无历史会话
                  </div>
                ) : (
                  <ul className="divide-y divide-slate-100 rounded-sm border border-slate-200 bg-white">
                    {recentCases.map(task => {
                      const m = statusMeta(task.status)
                      const active = task.id === currentTask?.id
                      const title = task.audioMeta?.title || task.formData?.video_url || '未命名会话'
                      return (
                        <li key={task.id}>
                          <button
                            type="button"
                            onClick={() => setCurrentTask(task.id)}
                            className={`flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left transition hover:bg-slate-50 ${active ? 'bg-slate-50' : ''}`}
                          >
                            <span className={`mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full ${m.dot}`} />
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-xs font-medium text-slate-800">{title}</span>
                              <span className="mt-0.5 block font-mono text-[10px] text-slate-400">
                                {shortId(task.id)} · {relativeTime(task.createdAt)}
                              </span>
                            </span>
                            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-300" />
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </section>
            </div>
          </ScrollArea>

          {/* 底部辅助操作 */}
          <footer className="shrink-0 border-t border-slate-200 px-3 py-2.5">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => emitWorkspaceCommand({ action: 'copy' })}
                className="inline-flex h-8 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-sm text-[11px] font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
              >
                <Copy className="h-3.5 w-3.5" />
                复制
              </button>
              <button
                type="button"
                onClick={() => emitWorkspaceCommand({ action: 'download' })}
                className="inline-flex h-8 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-sm text-[11px] font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
              >
                <Download className="h-3.5 w-3.5" />
                导出
              </button>
              <button
                type="button"
                onClick={() => emitWorkspaceCommand({ viewMode: 'preview', transcribe: 'toggle' })}
                className="inline-flex h-8 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-sm text-[11px] font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
                title="原文参照"
              >
                <FileText className="h-3.5 w-3.5" />
                原文
              </button>
            </div>
          </footer>
        </aside>
      </div>
    </div>
  )
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-2">
      <dt className="shrink-0 text-[11px] text-slate-500">{label}</dt>
      <dd className="min-w-0 truncate text-right">{value}</dd>
    </div>
  )
}

function TallyCell({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-0.5 font-mono text-base font-semibold tabular-nums ${tone}`}>{value}</div>
    </div>
  )
}

export default HomeLayout
