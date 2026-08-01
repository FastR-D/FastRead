'use client'

import { useEffect, useState } from 'react'
import {
  BrainCircuit,
  BookOpenCheck,
  Copy,
  Download,
  FileText,
  MessageSquare,
  SearchCheck,
  ShieldCheck,
  SquareStack,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

interface VersionNote {
  ver_id: string
  model_name?: string
  style?: string
  created_at?: string
}

interface VerificationSnapshot {
  overall?: { status?: string }
  claim_counts?: {
    total?: number
    online_supported?: number
    online_refuted?: number
    online_checked?: number
  }
}

interface NoteHeaderProps {
  currentTask?: {
    markdown: VersionNote[] | string
    insights?: { verification?: VerificationSnapshot }
  }
  isMultiVersion: boolean
  currentVerId: string
  setCurrentVerId: (id: string) => void
  modelName: string
  style: string
  noteStyles: { value: string; label: string }[]
  onCopy: () => void
  onDownload: () => void
  createAt?: string | Date
  showTranscribe: boolean
  setShowTranscribe: (show: boolean) => void
  showChat?: false | 'half' | 'full'
  setShowChat?: (mode: false | 'half' | 'full') => void
  viewMode: 'report' | 'verify' | 'map' | 'preview' | 'cards'
  setViewMode: (mode: 'report' | 'verify' | 'map' | 'preview' | 'cards') => void
}

const VERDICT_TONE: Record<string, string> = {
  supported: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  refuted: 'bg-red-50 text-red-700 border-red-200',
  mixed: 'bg-amber-50 text-amber-700 border-amber-200',
  insufficient: 'bg-slate-100 text-slate-600 border-slate-200',
  data_void: 'bg-orange-50 text-orange-700 border-orange-200',
  source_risk: 'bg-red-50 text-red-700 border-red-200',
}

export function MarkdownHeader({
  currentTask,
  isMultiVersion,
  currentVerId,
  setCurrentVerId,
  modelName,
  style,
  noteStyles,
  onCopy,
  onDownload,
  createAt,
  showTranscribe,
  setShowTranscribe,
  showChat,
  setShowChat,
  viewMode,
  setViewMode,
}: NoteHeaderProps) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let timer: NodeJS.Timeout
    if (copied) {
      timer = setTimeout(() => setCopied(false), 2000)
    }
    return () => clearTimeout(timer)
  }, [copied])

  const handleCopy = () => {
    onCopy()
    setCopied(true)
  }

  const styleName = noteStyles.find(v => v.value === style)?.label || style

  const formatDate = (date: string | Date | undefined) => {
    if (!date) return ''
    const d = typeof date === 'string' ? new Date(date) : date
    if (isNaN(d.getTime())) return ''
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }

  const verdict = currentTask?.insights?.verification
  const verdictStatus = verdict?.overall?.status
  const verdictCounts = verdict?.claim_counts
  const verdictTone = verdictStatus ? VERDICT_TONE[verdictStatus] || 'bg-slate-100 text-slate-600 border-slate-200' : ''

  const viewBtn = (
    active: boolean,
    onClick: () => void,
    icon: React.ReactNode,
    label: string,
    tip: string,
    primary = false,
  ) => (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={onClick}
            className={`inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-sm px-2.5 text-xs font-medium transition ${
              active
                ? primary
                  ? 'bg-slate-900 text-white hover:bg-slate-700'
                  : 'bg-slate-100 text-slate-900 hover:bg-slate-200'
                : 'text-slate-500 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            {icon}
            <span>{label}</span>
          </button>
        </TooltipTrigger>
        <TooltipContent>{tip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )

  return (
    <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-2">
      {/* 左侧：版本 + 元数据 + 判定 */}
      <div className="flex flex-wrap items-center gap-2">
        {isMultiVersion && (
          <Select value={currentVerId} onValueChange={setCurrentVerId}>
            <SelectTrigger className="h-7 w-[140px] text-xs">
              <div className="flex items-center font-mono">
                {(() => {
                  const currentIndex = currentTask?.markdown.findIndex(v => v.ver_id === currentVerId)
                  return currentIndex !== -1 ? `版本（${currentVerId.slice(-6)}）` : ''
                })()}
              </div>
            </SelectTrigger>
            <SelectContent>
              {(currentTask?.markdown || []).map(v => {
                const shortId = v.ver_id.slice(-6)
                return (
                  <SelectItem key={v.ver_id} value={v.ver_id}>
                    {`版本（${shortId}）`}
                  </SelectItem>
                )
              })}
            </SelectContent>
          </Select>
        )}

        {modelName && (
          <span className="inline-flex items-center rounded-sm border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[11px] text-slate-600">
            {modelName}
          </span>
        )}
        {styleName && (
          <span className="inline-flex items-center rounded-sm border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[11px] text-slate-600">
            {styleName}
          </span>
        )}

        {createAt && (
          <span className="font-mono text-[11px] text-slate-400">{formatDate(createAt)}</span>
        )}

        {verdictStatus && (
          <span className={`inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-[11px] font-medium ${verdictTone}`}>
            <ShieldCheck className="h-3 w-3" />
            {verdictStatus}
            {verdictCounts && (
              <span className="font-mono opacity-70">
                ({verdictCounts.online_supported ?? 0}/{verdictCounts.online_refuted ?? 0}/{verdictCounts.total ?? 0})
              </span>
            )}
          </span>
        )}
      </div>

      {/* 右侧：视图切换 + 工具操作 */}
      <div className="flex items-center gap-1">
        {/* 视图切换：阅读报告为主，联网核实是证据层 */}
        {viewBtn(
          viewMode === 'report',
          () => setViewMode('report'),
          <BookOpenCheck className="h-3.5 w-3.5" />,
          '阅读报告',
          'NotebookLM 式关键问题阅读报告',
          true,
        )}
        {viewBtn(
          viewMode === 'verify',
          () => setViewMode('verify'),
          <SearchCheck className="h-3.5 w-3.5" />,
          '联网核实',
          '联网核实报告',
        )}
        {viewBtn(
          viewMode === 'preview',
          () => setViewMode('preview'),
          <FileText className="h-3.5 w-3.5" />,
          'Markdown',
          'Markdown 笔记',
        )}
        {viewBtn(
          viewMode === 'map',
          () => setViewMode(viewMode === 'map' ? 'preview' : 'map'),
          <BrainCircuit className="h-3.5 w-3.5" />,
          '导图',
          '思维导图',
        )}
        {viewBtn(
          viewMode === 'cards',
          () => setViewMode(viewMode === 'cards' ? 'preview' : 'cards'),
          <SquareStack className="h-3.5 w-3.5" />,
          '卡片',
          '知识卡片',
        )}

        <div className="mx-1 h-5 w-px bg-slate-200" />

        {/* 工具操作 */}
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                onClick={() => setShowTranscribe(!showTranscribe)}
                variant={showTranscribe ? 'secondary' : 'ghost'}
                size="sm"
                className="h-8 px-2 text-xs"
              >
                <span>原文参照</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>打开转写文本</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        {setShowChat && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  onClick={() => setShowChat(showChat ? false : 'half')}
                  variant={showChat ? 'secondary' : 'ghost'}
                  size="sm"
                  className="h-8 px-2 text-xs"
                >
                  <MessageSquare className="mr-1.5 h-3.5 w-3.5" />
                  <span>AI 问答</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>基于笔记内容的 AI 问答</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        <div className="mx-1 h-5 w-px bg-slate-200" />

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button onClick={handleCopy} variant="ghost" size="sm" className="h-8 px-2 text-xs">
                <Copy className="mr-1.5 h-3.5 w-3.5" />
                <span>{copied ? '已复制' : '复制'}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>复制内容</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button onClick={onDownload} variant="ghost" size="sm" className="h-8 px-2 text-xs">
                <Download className="mr-1.5 h-3.5 w-3.5" />
                <span>导出</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>下载为 Markdown 文件</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </div>
  )
}
