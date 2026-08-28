import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileSearch,
  FileText,
  Files,
  GalleryVerticalEnd,
  Highlighter,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Pencil,
  Quote,
  Save,
  Search,
  Trash2,
  X,
} from 'lucide-react'
import { Input } from '@/components/ui/input'
import { resolve_backend_resource_url } from '@/services/note'
import {
  createAnnotation,
  deleteAnnotation,
  listAnnotations,
  updateAnnotation,
  type PaperAnnotation,
} from '@/services/evidenceHub'
import type { Task } from '@/store/taskStore'
import { cn } from '@/lib/utils'
import { findQuoteRange } from '@/utils/workspaceNavigation'
import toast from 'react-hot-toast'

interface PaperSourceViewProps {
  task: Task | null
  page?: number
  quote?: string
  onLocationChange: (page: number, quote?: string) => void
}

export default function PaperSourceView({ task, page, quote, onLocationChange }: PaperSourceViewProps) {
  const paper = task?.paperDocument
  const [query, setQuery] = useState('')
  const [activePage, setActivePage] = useState(1)
  const [annotationQuery, setAnnotationQuery] = useState('')
  const [annotations, setAnnotations] = useState<PaperAnnotation[]>([])
  const [selection, setSelection] = useState<{ page: number; start: number; end: number; quote: string } | null>(null)
  const [selectionNote, setSelectionNote] = useState('')
  const [savingSelection, setSavingSelection] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingNote, setEditingNote] = useState('')
  const [activeAnnotationId, setActiveAnnotationId] = useState<string | null>(null)
  const [pagesOpen, setPagesOpen] = useState(false)
  const [annotationsOpen, setAnnotationsOpen] = useState(false)
  const [sourceMode, setSourceMode] = useState<'layout' | 'text'>('layout')
  const quoteRef = useRef<HTMLElement>(null)
  const pageTextRef = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    setQuery('')
    const totalPages = paper?.page_count_total || paper?.page_count || paper?.pages?.length || 1
    const requestedPage = page && page >= 1 && page <= totalPages ? page : undefined
    setActivePage(requestedPage || paper?.pages?.[0]?.page || 1)
  }, [page, paper?.id, paper?.page_count, paper?.page_count_total, paper?.pages])

  useEffect(() => {
    if (!task?.id || !paper) {
      setAnnotations([])
      return
    }
    let cancelled = false
    listAnnotations(task.id)
      .then(items => { if (!cancelled) setAnnotations(items) })
      .catch(() => { if (!cancelled) setAnnotations([]) })
    return () => { cancelled = true }
  }, [paper, task?.id])

  const originalPages = useMemo(() => {
    const parsed = new Map((paper?.pages || []).map(item => [item.page, item]))
    const total = paper?.page_count_total || paper?.page_count || paper?.pages?.length || 0
    return Array.from({ length: total }, (_, index) => parsed.get(index + 1) || {
      page: index + 1,
      text: '',
      start: 0,
      end: 0,
    })
  }, [paper?.page_count, paper?.page_count_total, paper?.pages])
  const visiblePages = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return sourceMode === 'layout' ? originalPages : paper?.pages || []
    return (paper?.pages || []).filter(page =>
      page.text.toLowerCase().includes(keyword) || String(page.page) === keyword
    )
  }, [originalPages, paper?.pages, query, sourceMode])

  const selectedPage = (paper?.pages || []).find(page => page.page === activePage)
    || originalPages.find(page => page.page === activePage)
    || visiblePages[0]
    || paper?.pages?.[0]
  const sourceHref = resolve_backend_resource_url(paper?.pdf_url || paper?.resolved_source_url || paper?.source_url)
  const sourcePageHref = sourceHref
    ? `${sourceHref}#page=${selectedPage?.page || 1}&zoom=page-width&view=FitH`
    : ''
  const quoteRange = useMemo(
    () => selectedPage && quote ? findQuoteRange(selectedPage.text, quote) : null,
    [quote, selectedPage],
  )
  const pageAnnotations = useMemo(
    () => annotations.filter(item => item.page === selectedPage?.page),
    [annotations, selectedPage?.page],
  )
  const visibleAnnotations = useMemo(() => {
    const keyword = annotationQuery.trim().toLowerCase()
    if (!keyword) return annotations
    return annotations.filter(item => `${item.exact_quote} ${item.note} ${item.page}`.toLowerCase().includes(keyword))
  }, [annotationQuery, annotations])
  const navigationPages = sourceMode === 'layout' ? originalPages : paper?.pages || []
  const pageIndex = navigationPages.findIndex(item => item.page === selectedPage?.page)
  const previousPage = pageIndex > 0 ? navigationPages[pageIndex - 1] : undefined
  const nextPage = pageIndex >= 0 && pageIndex < navigationPages.length - 1
    ? navigationPages[pageIndex + 1]
    : undefined
  const pageSummaries = useMemo(() => {
    const pages = paper?.pages || []
    const lineCounts = new Map<string, number>()
    const pageLines = pages.map(item => item.text
      .split(/\r?\n/)
      .map(line => line.replace(/\s+/g, ' ').trim())
      .filter(Boolean))

    pageLines.forEach(lines => {
      new Set(lines.map(line => line.toLowerCase())).forEach(line => {
        lineCounts.set(line, (lineCounts.get(line) || 0) + 1)
      })
    })

    return new Map(pages.map((item, index) => {
      const useful = pageLines[index].filter(line => {
        const normalized = line.toLowerCase()
        if (/^(published as|preprint|arxiv:|https?:\/\/|\d{1,3})\b/i.test(line)) return false
        return (lineCounts.get(normalized) || 0) < 2
      })
      const summary = (useful.length ? useful : pageLines[index])
        .slice(0, 3)
        .join(' ')
        .replace(/\s+/g, ' ')
        .replace(/^published as a (?:conference|workshop) paper at\s+[a-z][a-z0-9&. -]*?\s+\d{4}\s+/i, '')
        .replace(/^(?:preprint|arxiv:)\s*[^ ]+\s*/i, '')
        .slice(0, 72)
      return [item.page, summary || '本页暂无可用摘要']
    }))
  }, [paper?.pages])

  const goToPage = (targetPage: number) => {
    setActivePage(targetPage)
    onLocationChange(targetPage)
  }

  useEffect(() => {
    if (!quoteRange) return
    setSourceMode('text')
    const timer = setTimeout(() => quoteRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 60)
    return () => clearTimeout(timer)
  }, [quoteRange, selectedPage?.page])

  useEffect(() => {
    if (!activeAnnotationId) return
    const timer = setTimeout(() => {
      document.querySelector(`[data-annotation-id="${activeAnnotationId}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 60)
    return () => clearTimeout(timer)
  }, [activeAnnotationId, selectedPage?.page])

  const captureSelection = () => {
    const nativeSelection = window.getSelection()
    const container = pageTextRef.current
    if (!nativeSelection || nativeSelection.isCollapsed || !container || !selectedPage) return
    const range = nativeSelection.getRangeAt(0)
    if (!container.contains(range.commonAncestorContainer)) return
    const prefix = range.cloneRange()
    prefix.selectNodeContents(container)
    prefix.setEnd(range.startContainer, range.startOffset)
    const start = prefix.toString().length
    const exactQuote = range.toString()
    if (!exactQuote || selectedPage.text.slice(start, start + exactQuote.length) !== exactQuote) return
    setSelection({ page: selectedPage.page, start, end: start + exactQuote.length, quote: exactQuote })
    setSelectionNote('')
  }

  const saveSelection = async () => {
    if (!selection || !task) return
    setSavingSelection(true)
    try {
      const created = await createAnnotation(task.id, {
        page: selection.page,
        start_offset: selection.start,
        end_offset: selection.end,
        exact_quote: selection.quote,
        note: selectionNote,
      })
      setAnnotations(current => [...current, created].sort((a, b) => a.page - b.page || a.start_offset - b.start_offset))
      setSelection(null)
      setSelectionNote('')
      window.getSelection()?.removeAllRanges()
      toast.success('摘录已保存')
    }
    finally {
      setSavingSelection(false)
    }
  }

  const saveEdit = async (annotation: PaperAnnotation) => {
    if (!task) return
    const updated = await updateAnnotation(task.id, annotation.id, { note: editingNote })
    setAnnotations(current => current.map(item => item.id === updated.id ? updated : item))
    setEditingId(null)
  }

  const removeAnnotation = async (annotation: PaperAnnotation) => {
    if (!task || !window.confirm('删除这条摘录和批注？')) return
    await deleteAnnotation(task.id, annotation.id)
    setAnnotations(current => current.filter(item => item.id !== annotation.id))
    if (activeAnnotationId === annotation.id) setActiveAnnotationId(null)
  }

  const renderPageText = () => {
    const text = selectedPage?.text || '本页没有可提取文字。'
    const boundaries = new Set([0, text.length])
    if (quoteRange) {
      boundaries.add(quoteRange.start)
      boundaries.add(quoteRange.end)
    }
    for (const item of pageAnnotations) {
      boundaries.add(Math.max(0, Math.min(text.length, item.start_offset)))
      boundaries.add(Math.max(0, Math.min(text.length, item.end_offset)))
    }
    const points = [...boundaries].sort((a, b) => a - b)
    return points.slice(0, -1).map((start, index) => {
      const end = points[index + 1]
      const value = text.slice(start, end)
      const userAnnotation = pageAnnotations.find(item => start >= item.start_offset && end <= item.end_offset)
      const aiHighlighted = Boolean(quoteRange && start >= quoteRange.start && end <= quoteRange.end)
      if (!userAnnotation && !aiHighlighted) return <span key={`${start}-${end}`}>{value}</span>
      return (
        <mark
          key={`${start}-${end}`}
          ref={aiHighlighted && quoteRange?.start === start ? quoteRef : undefined}
          data-annotation-id={userAnnotation?.id}
          className={cn(
            'scroll-mt-24 rounded px-0.5 text-slate-950',
            userAnnotation ? 'bg-blue-200 ring-1 ring-blue-300' : 'bg-amber-200 ring-2 ring-amber-300',
            userAnnotation?.id === activeAnnotationId && 'ring-2 ring-blue-600',
          )}
        >
          {value}
        </mark>
      )
    })
  }

  if (!task || !paper) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center">
        <div>
          <FileSearch className="mx-auto h-9 w-9 text-slate-300" />
          <p className="mt-3 text-sm font-medium text-slate-700">尚无分页论文原文</p>
          <p className="mt-1 text-xs text-slate-500">请先导入 PDF，或提交包含可访问 PDF 的论文详情页。</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 bg-slate-50/50">
      {pagesOpen && <aside className="flex w-52 min-h-0 shrink-0 flex-col border-r border-slate-200 bg-white 2xl:w-60">
        <div className="border-b border-slate-200 p-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-800">
            <Files className="h-4 w-4" />
            分页原文
          </div>
          <div className="relative mt-2">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <Input
              value={query}
              onChange={event => setQuery(event.target.value)}
              className="h-8 pl-8 text-xs"
              placeholder="搜索页内文字或页码"
            />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {visiblePages.map(page => (
            <button
              key={page.page}
              type="button"
              onClick={() => {
                goToPage(page.page)
              }}
              className={cn(
                'mb-1 w-full rounded-md px-3 py-2 text-left text-xs transition',
                selectedPage?.page === page.page
                  ? 'bg-slate-900 text-white'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              )}
            >
              <span className="font-mono">第 {page.page} 页</span>
              <span className={cn(
                'mt-1 block truncate',
                selectedPage?.page === page.page ? 'text-slate-300' : 'text-slate-400'
              )}>
                {pageSummaries.get(page.page)}
              </span>
            </button>
          ))}
          {visiblePages.length === 0 && (
            <p className="px-3 py-6 text-center text-xs text-slate-400">没有匹配页面</p>
          )}
        </div>
      </aside>}

      <main className="min-w-0 flex-1 overflow-y-auto">
        <article className="mx-auto max-w-[920px] px-4 py-5 pb-16 sm:px-6 2xl:max-w-[1040px]">
          <header className="mb-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setPagesOpen(value => !value)}
                  className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 px-2.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
                  aria-label={pagesOpen ? '收起页目录' : '展开页目录'}
                >
                  {pagesOpen ? <PanelLeftClose className="h-3.5 w-3.5" /> : <PanelLeftOpen className="h-3.5 w-3.5" />}
                  页目录
                </button>
                <button
                  type="button"
                  disabled={!previousPage}
                  onClick={() => previousPage && goToPage(previousPage.page)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-35"
                  aria-label="上一页"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="min-w-20 text-center font-mono text-[11px] text-slate-500">
                  {selectedPage?.page || 1} / {sourceMode === 'layout' ? (paper.page_count_total || paper.page_count || paper.pages.length) : paper.pages.length}
                </span>
                <button
                  type="button"
                  disabled={!nextPage}
                  onClick={() => nextPage && goToPage(nextPage.page)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-35"
                  aria-label="下一页"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
              <div className="flex items-center gap-1">
                {sourceHref && <div className="mr-1 flex rounded-md bg-slate-100 p-0.5" aria-label="原文显示方式">
                  <button
                    type="button"
                    onClick={() => setSourceMode('layout')}
                    className={cn(
                      'inline-flex h-7 items-center gap-1 rounded px-2 text-[11px] font-medium transition',
                      sourceMode === 'layout' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800',
                    )}
                  >
                    <GalleryVerticalEnd className="h-3.5 w-3.5" /> 原版页（含图表）
                  </button>
                  <button
                    type="button"
                    onClick={() => setSourceMode('text')}
                    className={cn(
                      'inline-flex h-7 items-center gap-1 rounded px-2 text-[11px] font-medium transition',
                      sourceMode === 'text' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800',
                    )}
                  >
                    <FileText className="h-3.5 w-3.5" /> 可摘录文本
                  </button>
                </div>}
                <button
                  type="button"
                  onClick={() => setAnnotationsOpen(value => !value)}
                  className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 px-2.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
                  aria-label={annotationsOpen ? '收起摘录本' : '展开摘录本'}
                >
                  {annotationsOpen ? <PanelRightClose className="h-3.5 w-3.5" /> : <PanelRightOpen className="h-3.5 w-3.5" />}
                  摘录本（{annotations.length}）
                </button>
              </div>
            </div>
            <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-slate-400">
                Source · Page {selectedPage?.page || 1} / {sourceMode === 'layout' ? (paper.page_count_total || paper.page_count || paper.pages.length) : paper.pages.length}
              </div>
              <h1 className="mt-1 truncate text-base font-semibold text-slate-900">{paper.title}</h1>
              <p className="mt-1 text-xs text-slate-500">
                {(paper.authors || []).slice(0, 4).join('、') || '作者未识别'}
                {paper.year ? ` · ${paper.year}` : ''}
              </p>
            </div>
            {sourceHref && (
              <a
                href={sourceHref}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 px-3 text-xs font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
              >
                打开原 PDF <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
            </div>
          </header>
          {(paper.text_truncated || paper.pages.length < (paper.page_count_total || paper.page_count || paper.pages.length)) && (
            <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              文本层覆盖 {paper.pages.length} / {paper.page_count_total || paper.page_count} 个有可提取文本的页面；原版 PDF 的全部 {paper.page_count_total || paper.page_count} 页仍可逐页查看，未提取文本的页面不会进入检索、引用或报告。
            </div>
          )}
          {quote && (
            <div className={`mb-4 rounded-md border px-4 py-3 text-xs leading-5 ${
              quoteRange
                ? 'border-amber-300 bg-amber-50 text-amber-950'
                : 'border-slate-300 bg-slate-100 text-slate-700'
            }`}>
              <div className="flex items-center gap-1.5 font-semibold">
                <Highlighter className="h-3.5 w-3.5" />
                {quoteRange ? '已定位并高亮引用原句' : '已定位引用页，抽取文本未逐字命中原句'}
              </div>
              <blockquote className="mt-1.5 border-l-2 border-current/30 pl-2">“{quote}”</blockquote>
            </div>
          )}
          {selection && (
            <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-3 shadow-sm" data-testid="annotation-toolbar">
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2 text-xs font-semibold text-blue-900">
                  <Quote className="h-4 w-4" />
                  <span className="truncate">“{selection.quote}”</span>
                </div>
                <button type="button" onClick={() => setSelection(null)} className="text-blue-500"><X className="h-4 w-4" /></button>
              </div>
              <textarea
                value={selectionNote}
                onChange={event => setSelectionNote(event.target.value)}
                className="mt-2 min-h-16 w-full rounded-md border border-blue-200 bg-white px-3 py-2 text-xs outline-none focus:border-blue-400"
                placeholder="添加批注（可选）"
                maxLength={10000}
              />
              <button
                type="button"
                disabled={savingSelection}
                onClick={saveSelection}
                className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-md bg-blue-700 px-3 text-xs font-medium text-white disabled:opacity-50"
              >
                <Save className="h-3.5 w-3.5" /> {savingSelection ? '保存中…' : '保存蓝色摘录'}
              </button>
            </div>
          )}
          {sourceMode === 'layout' && sourcePageHref ? (
            <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-2.5">
                <div>
                  <div className="text-xs font-semibold text-slate-800">原版 PDF · 第 {selectedPage?.page || 1} 页</div>
                  <p className="mt-0.5 text-[10px] text-slate-500">保留论文中的图、表、公式和版式；摘录或全文搜索请切换到“可摘录文本”。</p>
                </div>
                <a href={sourcePageHref} target="_blank" rel="noreferrer" className="text-xs font-medium text-blue-700 hover:underline">
                  在新窗口查看本页
                </a>
              </div>
              <iframe
                key={sourcePageHref}
                src={sourcePageHref}
                title={`原版 PDF 第 ${selectedPage?.page || 1} 页（含图表）`}
                className="h-[min(76vh,980px)] min-h-[680px] w-full bg-slate-100"
              />
            </section>
          ) : <section className="rounded-lg border border-slate-200 bg-white px-6 py-8 shadow-sm sm:px-10 lg:px-14">
            <div className="mb-6 flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <span className="text-sm font-semibold text-slate-900">第 {selectedPage?.page || 1} 页 · 可摘录文本</span>
                <p className="mt-1 text-[10px] text-slate-500">该视图来自 PDF 文本抽取，不包含图表像素与原始排版；图表请查看“原版页”。</p>
              </div>
              <span className="font-mono text-[10px] text-slate-400">
                {selectedPage?.text.length || 0} chars
              </span>
            </div>
            <p
              ref={pageTextRef}
              onMouseUp={captureSelection}
              className="whitespace-normal break-normal font-serif text-[16px] leading-[1.9] text-slate-800 selection:bg-blue-200"
              data-testid="paper-page-text"
            >
              {renderPageText()}
            </p>
          </section>}
        </article>
      </main>
      {annotationsOpen && <aside className="flex w-72 min-h-0 shrink-0 flex-col border-l border-slate-200 bg-white 2xl:w-80">
        <div className="border-b border-slate-200 p-3">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-800">
            <span className="flex items-center gap-2"><Highlighter className="h-4 w-4 text-blue-600" />摘录本</span>
            <span className="font-mono text-[10px] text-slate-400">{annotations.length}</span>
          </div>
          <div className="relative mt-2">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <Input value={annotationQuery} onChange={event => setAnnotationQuery(event.target.value)} className="h-8 pl-8 text-xs" placeholder="搜索摘录或批注" />
          </div>
          <p className="mt-2 text-[10px] leading-4 text-slate-400">拖选页内原文后保存。蓝色为用户摘录，琥珀色为 AI 引用定位。</p>
        </div>
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
          {visibleAnnotations.map(annotation => (
            <article key={annotation.id} className="rounded-md border border-blue-100 bg-blue-50/50 p-3">
              <button
                type="button"
                className="w-full text-left"
                onClick={() => {
                  setActivePage(annotation.page)
                  setActiveAnnotationId(annotation.id)
                  setSourceMode('text')
                  onLocationChange(annotation.page)
                }}
              >
                <div className="font-mono text-[10px] font-semibold text-blue-700">PAGE {annotation.page}</div>
                <blockquote className="mt-1 line-clamp-4 text-xs leading-5 text-slate-700">“{annotation.exact_quote}”</blockquote>
              </button>
              {editingId === annotation.id ? (
                <div className="mt-2">
                  <textarea value={editingNote} onChange={event => setEditingNote(event.target.value)} className="min-h-16 w-full rounded border border-blue-200 bg-white p-2 text-xs" />
                  <div className="mt-1 flex gap-1">
                    <button type="button" onClick={() => saveEdit(annotation)} className="rounded bg-blue-700 px-2 py-1 text-[10px] text-white">保存</button>
                    <button type="button" onClick={() => setEditingId(null)} className="rounded border border-slate-200 px-2 py-1 text-[10px]">取消</button>
                  </div>
                </div>
              ) : (
                <p className="mt-2 text-[11px] leading-4 text-slate-500">{annotation.note || '暂无批注'}</p>
              )}
              <div className="mt-2 flex justify-end gap-1">
                <button type="button" title="编辑批注" onClick={() => { setEditingId(annotation.id); setEditingNote(annotation.note) }} className="rounded p-1 text-slate-400 hover:bg-white hover:text-slate-700"><Pencil className="h-3.5 w-3.5" /></button>
                <button type="button" title="删除摘录" onClick={() => removeAnnotation(annotation)} className="rounded p-1 text-slate-400 hover:bg-white hover:text-red-600"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            </article>
          ))}
          {!visibleAnnotations.length && <p className="px-3 py-8 text-center text-xs text-slate-400">尚无摘录</p>}
        </div>
      </aside>}
    </div>
  )
}
