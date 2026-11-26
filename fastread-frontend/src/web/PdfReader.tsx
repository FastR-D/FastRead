import 'pdfjs-dist/web/pdf_viewer.css'
import {
  Alert,
  Button,
  CanvasSurface,
  Loading,
  PanelHeader,
  Select,
  TextArea,
  TextField,
  Toolbar,
  SegmentedControl,
} from '@fastrd/ui-react'
import { API_BASE, assetUrl } from './urls'
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import PdfPage from './PdfPage'
import { pdfEngine } from './pdfEngine'
import { usePdfNavigation } from './usePdfNavigation'
import {
  ChevronLeft,
  ChevronRight,
  Search,
  ListTree,
  Minus,
  Plus,
  Highlighter,
  X,
  StickyNote,
  Pencil,
  Trash2,
  FileDown,
} from 'lucide-react'
type Row = Record<string, any>
type Props = {
  paper: Row
  version: string
  page: number
  setPage: (p: number) => void
  api: any
  summary: string
  setSummary: (s: string) => void
  onSaved: (s: string) => void
  companion?: ReactNode
  companionHeader?: ReactNode
  pane?: string
  onPane?: (s: string) => void
  onQuote?: (selection: Row) => void
  citation?: Row | null
  notebookNotes?: ReactNode
  panelId?: string
  labelledBy?: string
  notesOpen?: boolean
  onNotesOpen?: (open: boolean) => void
}
let worker: any
export default function PdfReader({
  paper,
  version,
  page,
  setPage,
  api,
  summary,
  setSummary,
  onSaved,
  companion,
  companionHeader,
  pane = 'notes',
  onPane,
  onQuote,
  citation,
  notebookNotes,
  panelId,
  labelledBy,
  notesOpen = true,
  onNotesOpen = () => {},
}: Props) {
  const host = useRef<HTMLDivElement>(null)
  const [document, setDocument] = useState<any>(null)
  const [width, setWidth] = useState(800)
  const [zoom, setZoom] = useState(1)
  const [fitPage, setFitPage] = useState(false)
  const [height, setHeight] = useState(600)
  const [aspect, setAspect] = useState(842 / 595)
  const [noteView, setNoteView] = useState('annotations')
  const [noteFilter, setNoteFilter] = useState('')
  const [highlightMode, setHighlightMode] = useState(false)
  const navigation = usePdfNavigation(document, setPage)
  const renderZoom = fitPage ? Math.min(1, (height - 32) / (width * aspect)) : zoom
  useEffect(() => {
    let dead = false
    if (document)
      void document
        .getPage(page)
        .then((p: any) => {
          const viewport = p.getViewport({ scale: 1 })
          if (!dead) setAspect(viewport.height / viewport.width)
        })
        .catch(() => {})
    return () => {
      dead = true
    }
  }, [document, page])
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [annotations, setAnnotations] = useState<Row[]>([])
  const [selection, setSelection] = useState<Row | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState('')
  const [editText, setEditText] = useState('')
  const summarySaved = useRef(paper.summary || '')
  const draftKey = `notes:${paper.id}`
  const annotationDraftKey = `annotation:${paper.id}:${version}:${page}`
  const [recovered, setRecovered] = useState(() => localStorage.getItem(draftKey) || '')
  useEffect(() => {
    if (!status) return
    const timer = window.setTimeout(() => setStatus(''), 3500)
    return () => window.clearTimeout(timer)
  }, [status])
  const base = `/papers/${paper.id}/annotations`
  const file = `${API_BASE}/papers/${paper.id}/file?version=${encodeURIComponent(version)}`
  async function reload() {
    setAnnotations((await api(`${base}?version=${encodeURIComponent(version)}`)).items)
  }
  async function perform(fn: () => Promise<void>) {
    setError('')
    setBusy(true)
    try {
      await fn()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  useEffect(() => {
    const observer = new ResizeObserver(entries => {
      setWidth(Math.max(200, entries[0].contentRect.width - 32))
      setHeight(entries[0].contentRect.height)
    })
    if (host.current) observer.observe(host.current)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    let dead = false,
      task: any
    setDocument(null)
    setError('')
    setAnnotations([])
    pdfEngine()
      .then(pdf => {
        if (dead) return
        worker ||= new pdf.PDFWorker()
        task = pdf.getDocument({
          url: file,
          worker,
          disableStream: true,
          disableAutoFetch: true,
          rangeChunkSize: 65536,
          cMapUrl: assetUrl('/vendor/pdfjs/cmaps/'),
          cMapPacked: true,
          standardFontDataUrl: assetUrl('/vendor/pdfjs/standard_fonts/'),
        })
        return task.promise.then((doc: any) => {
          if (!dead) setDocument(doc)
        })
      })
      .catch(e => {
        if (!dead) setError(`PDF 加载失败：${e.message}`)
      })
    api(`${base}?version=${encodeURIComponent(version)}`)
      .then((r: Row) => {
        if (!dead) setAnnotations(r.items)
      })
      .catch((e: Error) => {
        if (!dead) setError(e.message)
      })
    return () => {
      dead = true
      void task?.destroy()
    }
  }, [api, base, file, version])
  useEffect(() => {
    setStatus('')
    setEditing('')
    try {
      const draft = JSON.parse(localStorage.getItem(annotationDraftKey) || '{}')
      setNote(draft.note || '')
      setSelection(draft.selection || null)
    } catch {
      setNote('')
      setSelection(null)
    }
  }, [annotationDraftKey])
  function changeNote(value: string) {
    setNote(value)
    localStorage.setItem(annotationDraftKey, JSON.stringify({ note: value, selection }))
  }
  function clearSelection() {
    setSelection(null)
    window.getSelection()?.removeAllRanges()
    localStorage.setItem(annotationDraftKey, JSON.stringify({ note }))
  }
  useEffect(() => {
    if (summary !== summarySaved.current) localStorage.setItem(draftKey, summary)
    const warn = (e: BeforeUnloadEvent) => {
      if (summary !== summarySaved.current) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [summary, draftKey])
  const viewportAnchor = useRef({ page, fraction: 0 })
  const reportedPage = useRef<number | null>(null)
  const pendingJump = useRef<number | null>(page)
  const [forcedPage, setForcedPage] = useState(page)
  const [citationTarget, setCitationTarget] = useState(page)
  const lastCitation = useRef<Row | null | undefined>(undefined)
  useEffect(() => {
    if (lastCitation.current !== citation) {
      setCitationTarget(page)
      lastCitation.current = citation
    }
  }, [citation, page]) // A citation remains on its original page while scrolling.
  const jump = useCallback((number: number) => {
    const sheet = host.current?.querySelector<HTMLElement>(`[data-page="${number}"]`)
    if (sheet && host.current) {
      viewportAnchor.current = { page: number, fraction: -16 / sheet.offsetHeight }
      host.current.scrollTop = Math.max(0, sheet.offsetTop - 16)
    }
  }, [])
  useEffect(() => {
    if (!document) return
    const bounded = Math.max(1, Math.min(document.numPages, page))
    if (bounded !== page) {
      reportedPage.current = null
      setPage(bounded)
      return
    }
    if (reportedPage.current === page) {
      reportedPage.current = null
      return
    }
    pendingJump.current = page
    setForcedPage(page)
    jump(page)
    const sheet = host.current?.querySelector<HTMLElement>(`[data-page="${page}"]`)
    if (sheet?.dataset.ready === 'true') pendingJump.current = null
  }, [document, page, jump, setPage])
  const pageReady = useCallback(
    (number: number) => {
      if (pendingJump.current === number) {
        jump(number)
        pendingJump.current = null
      }
    },
    [jump]
  )
  const restoreAnchor = useCallback(() => {
    if (pendingJump.current !== null || !host.current) return
    const anchor = viewportAnchor.current
    const sheet = host.current.querySelector<HTMLElement>(`[data-page="${anchor.page}"]`)
    if (sheet)
      host.current.scrollTop = Math.max(0, sheet.offsetTop + anchor.fraction * sheet.offsetHeight)
  }, [])
  useLayoutEffect(() => {
    restoreAnchor()
  }, [width, renderZoom, restoreAnchor])
  function trackPage() {
    if (!host.current || pendingJump.current !== null) return
    const top =
      host.current.getBoundingClientRect().top + Math.min(160, host.current.clientHeight / 3)
    const sheets = Array.from(host.current.querySelectorAll<HTMLElement>('[data-page]'))
    const current = sheets.find(el => el.getBoundingClientRect().bottom > top)
    const number = Number(current?.dataset.page)
    if (current && number)
      viewportAnchor.current = {
        page: number,
        fraction: (host.current.scrollTop - current.offsetTop) / current.offsetHeight,
      }
    if (number && number !== page) {
      reportedPage.current = number
      setForcedPage(number)
      setPage(number)
    }
  }
  function capture(picked: Row) {
    if (highlightMode) {
      if (!busy)
        void perform(async () => {
          await api(base, 'POST', {
            version_id: version,
            page: picked.page,
            quote: picked.quote,
            rects: picked.rects,
            note: '',
          })
          window.getSelection()?.removeAllRanges()
          await reload()
          setStatus('高亮已保存')
        })
      return
    }
    let draftNote = note
    const key = `annotation:${paper.id}:${version}:${picked.page}`
    if (picked.page !== page) {
      try {
        draftNote = JSON.parse(localStorage.getItem(key) || '{}').note || ''
      } catch {
        draftNote = ''
      }
      reportedPage.current = picked.page
      setForcedPage(picked.page)
      setPage(picked.page)
      setNote(draftNote)
    }
    setSelection(picked)
    setNoteView('annotations')
    onNotesOpen(true)
    localStorage.setItem(key, JSON.stringify({ note: draftNote, selection: picked }))
  }
  return (
    <div
      onKeyDown={e => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
          e.preventDefault()
          navigation.setTool('find')
        }
      }}
      className={`pdf-workspace grid min-h-0 min-w-0 flex-1 grid-cols-1 gap-3 xl:grid-rows-[minmax(0,1fr)] ${notesOpen ? 'xl:grid-cols-[minmax(0,1fr)_22rem]' : 'notes-hidden'}`}
    >
      <div className="pdf-column fastui-section flex min-h-0 min-w-0 flex-col overflow-hidden">
        <Toolbar label="PDF 阅读工具" className="pdf-toolbar shrink-0">
          <Button
            variant="quiet"
            aria-label="文档目录"
            title="文档目录"
            aria-pressed={navigation.tool === 'outline'}
            onClick={() => navigation.setTool(navigation.tool === 'outline' ? null : 'outline')}
          >
            <ListTree size={16} />
          </Button>
          <Button
            variant="quiet"
            aria-label="文内查找"
            title="文内查找 (Ctrl / ⌘ F)"
            aria-pressed={navigation.tool === 'find'}
            onClick={() => navigation.setTool(navigation.tool === 'find' ? null : 'find')}
          >
            <Search size={16} />
          </Button>
          <span className="pdf-tool-divider" />
          <Button
            variant="quiet"
            aria-label="上一页"
            title="上一页"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            <ChevronLeft size={16} />
          </Button>
          <TextField
            htmlSize={3}
            aria-label="PDF 页码"
            type="number"
            min={1}
            max={document?.numPages || 1}
            value={page}
            onChange={e =>
              setPage(Math.max(1, Math.min(document?.numPages || 1, Number(e.target.value) || 1)))
            }
          />
          <span className="pdf-page-count">/ {document?.numPages || '…'}</span>
          <Button
            variant="quiet"
            aria-label="下一页"
            title="下一页"
            disabled={!document || page >= document.numPages}
            onClick={() => setPage(page + 1)}
          >
            <ChevronRight size={16} />
          </Button>
          <span className="pdf-tool-divider" />
          <Button
            variant="quiet"
            aria-label="缩小"
            title="缩小"
            disabled={renderZoom <= 0.25}
            onClick={() => {
              setFitPage(false)
              setZoom(Math.max(0.25, renderZoom - 0.25))
            }}
          >
            <Minus size={16} />
          </Button>
          <Select
            aria-label="PDF 缩放"
            value={fitPage ? 'page' : zoom}
            onChange={e => {
              setFitPage(e.target.value === 'page')
              if (e.target.value !== 'page') setZoom(Number(e.target.value))
            }}
          >
            <option value="page">适合页面</option>
            {[0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3].includes(zoom) ? null : (
              <option value={zoom}>{Math.round(zoom * 100)}%</option>
            )}
            {[0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3].map(z => (
              <option key={z} value={z}>
                {z === 1 ? '适合宽度' : `${z * 100}%`}
              </option>
            ))}
          </Select>
          <Button
            variant="quiet"
            aria-label="放大"
            title="放大"
            disabled={renderZoom >= 3}
            onClick={() => {
              setFitPage(false)
              setZoom(Math.min(3, renderZoom + 0.25))
            }}
          >
            <Plus size={16} />
          </Button>
          <span className="pdf-tool-divider" />
          <Button
            variant="quiet"
            aria-label="高亮文本"
            title="高亮文本：选文即保存"
            aria-pressed={highlightMode}
            onClick={() => setHighlightMode(!highlightMode)}
          >
            <Highlighter size={16} />
          </Button>
          <Button
            variant="quiet"
            aria-label="查看批注"
            title="查看批注"
            onClick={() => {
              setNoteView('annotations')
              onPane?.('notes')
              onNotesOpen(true)
            }}
          >
            <StickyNote size={16} />
          </Button>
        </Toolbar>
        {navigation.tool === 'find' && (
          <div className="pdf-findbar" role="search" aria-label="文内查找">
            <TextField
              autoFocus
              aria-label="查找文档内容"
              placeholder="在文档中查找"
              value={navigation.query}
              onChange={e => navigation.setQuery(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  navigation.move(e.shiftKey ? -1 : 1)
                }
                if (e.key === 'Escape') navigation.setTool(null)
              }}
            />
            <span role="status">
              {navigation.searching
                ? '查找中…'
                : navigation.query
                  ? `${navigation.active + 1} / ${navigation.matches.length}`
                  : ''}
            </span>
            <Button
              variant="quiet"
              aria-label="上一个匹配"
              disabled={!navigation.matches.length}
              onClick={() => navigation.move(-1)}
            >
              <ChevronLeft size={15} />
            </Button>
            <Button
              variant="quiet"
              aria-label="下一个匹配"
              disabled={!navigation.matches.length}
              onClick={() => navigation.move(1)}
            >
              <ChevronRight size={15} />
            </Button>
            <Button variant="quiet" aria-label="关闭查找" onClick={() => navigation.setTool(null)}>
              <X size={15} />
            </Button>
            {navigation.error && <span role="alert">{navigation.error}</span>}
          </div>
        )}
        {navigation.tool === 'outline' && (
          <nav className="pdf-outline" aria-label="文档目录">
            {navigation.outline.length ? (
              navigation.outline.map((item, i) => (
                <Button
                  key={i}
                  variant="quiet"
                  style={{ paddingLeft: 12 + item.depth * 12 }}
                  onClick={() => {
                    setPage(item.page)
                    navigation.setTool(null)
                  }}
                >
                  <span>{item.title}</span>
                  <small>{item.page}</small>
                </Button>
              ))
            ) : (
              <p>{navigation.error || '此文档没有内嵌目录，可通过页码跳转。'}</p>
            )}
          </nav>
        )}
        {selection && onQuote && (
          <Toolbar label="选文操作" className="selection-actions shrink-0">
            <span>已选原文</span>
            <Button
              onClick={() => {
                onQuote({ ...selection, paper_id: paper.id, version_id: version })
                onNotesOpen(true)
              }}
              type="button"
              variant="primary"
            >
              问这段
            </Button>
            <Button
              className="quiet"
              onClick={() => {
                setNoteView('annotations')
                onPane?.('notes')
                onNotesOpen(true)
              }}
              type="button"
              variant="quiet"
            >
              添加批注
            </Button>
            <Button className="quiet" onClick={clearSelection} type="button" variant="quiet">
              取消
            </Button>
          </Toolbar>
        )}
        <CanvasSurface
          grid={false}
          role="region"
          aria-label="PDF 原文"
          tabIndex={0}
          className="pdf-scroll relative h-[60dvh] min-w-0 overflow-auto p-4 xl:h-auto xl:min-h-0 xl:flex-1"
          ref={host}
          onScroll={trackPage}
        >
          {!document && <Loading label="正在载入 PDF…" />}
          {document &&
            Array.from({ length: document.numPages }, (_, index) => (
              <PdfPage
                key={`${version}:${index + 1}`}
                document={document}
                page={index + 1}
                width={width}
                zoom={renderZoom}
                host={host}
                annotations={annotations}
                citation={
                  navigation.tool === 'find' && navigation.hit?.page === index + 1
                    ? navigation.hit
                    : citationTarget === index + 1
                      ? citation
                      : null
                }
                onCapture={capture}
                onReady={pageReady}
                onMeasure={restoreAnchor}
                force={forcedPage === index + 1}
              />
            ))}
        </CanvasSurface>
      </div>
      {notesOpen && (
        <div className="reading-notes fastui-section min-h-0 min-w-0 xl:overflow-auto">
          {companionHeader}
          <div
            className="research-panel"
            id={panelId}
            role={panelId ? 'tabpanel' : undefined}
            aria-labelledby={labelledBy}
          >
            {pane !== 'notes' ? (
              companion
            ) : (
              <>
                <PanelHeader className="research-panel-heading">
                  <h2 className="fastui-heading m-0 text-base">笔记</h2>
                  <span>{annotations.length} 条批注</span>
                </PanelHeader>
                <SegmentedControl
                  className="note-sections"
                  label="笔记分类"
                  value={noteView}
                  onChange={setNoteView}
                  options={[
                    { value: 'annotations', label: '批注' },
                    { value: 'summary', label: '阅读笔记' },
                    { value: 'saved', label: '收藏' },
                  ]}
                />
                {noteView === 'annotations' && (
                  <div className="notes-annotations">
                    <form
                      onSubmit={e => {
                        e.preventDefault()
                        void perform(async () => {
                          await api(base, 'POST', {
                            version_id: version,
                            page: selection?.page || page,
                            quote: selection?.quote || '',
                            rects: selection?.rects || [],
                            note,
                          })
                          setSelection(null)
                          window.getSelection()?.removeAllRanges()
                          setNote('')
                          localStorage.removeItem(annotationDraftKey)
                          await reload()
                          setStatus('批注已保存')
                        })
                      }}
                      className="annotation-composer"
                    >
                      {selection && (
                        <div className="annotation-selection fastui-section grid gap-3 p-3">
                          <div className="annotation-selection-header flex flex-wrap items-center justify-between gap-2">
                            <span>选中原文 · 第 {selection.page} 页</span>
                            <Button
                              type="button"
                              className="quiet"
                              onClick={clearSelection}
                              variant="quiet"
                            >
                              取消选文
                            </Button>
                          </div>
                          <blockquote className="fastui-section m-0 max-h-48 overflow-auto p-3 break-words">
                            {selection.quote}
                          </blockquote>
                        </div>
                      )}
                      <label className="fastui-field">
                        <span>第 {page} 页 · 新批注</span>
                        <TextArea
                          aria-label="当前页批注"
                          value={note}
                          onChange={e => changeNote(e.target.value)}
                          maxLength={10000}
                          rows={3}
                          placeholder="记录批注…"
                          className="w-full"
                        />
                      </label>
                      <Button
                        disabled={busy || (!note.trim() && !selection)}
                        type="submit"
                        variant="primary"
                      >
                        保存批注
                      </Button>
                    </form>
                    {!!annotations.length && (
                      <TextField
                        aria-label="筛选批注"
                        placeholder="筛选批注…"
                        value={noteFilter}
                        onChange={e => setNoteFilter(e.target.value)}
                      />
                    )}
                    {!annotations.length && (
                      <div className="notes-empty">
                        <Highlighter size={24} />
                        <p>选中原文，留下第一条批注</p>
                      </div>
                    )}
                    <div className="annotation-list">
                      {annotations
                        .filter(a =>
                          `${a.note} ${a.quote}`.toLowerCase().includes(noteFilter.toLowerCase())
                        )
                        .sort((a, b) => a.page - b.page)
                        .map(a => (
                          <article
                            key={a.id}
                            className={a.page === page ? 'current-page-note' : ''}
                          >
                            <Button
                              className="page-link"
                              onClick={() => setPage(a.page)}
                              type="button"
                              variant="quiet"
                            >
                              第 {a.page} 页
                            </Button>
                            {a.quote && (
                              <blockquote className="fastui-section m-0 max-h-48 overflow-auto p-3 break-words">
                                {a.quote}
                              </blockquote>
                            )}
                            {editing === a.id ? (
                              <>
                                <TextArea
                                  aria-label="编辑批注"
                                  value={editText}
                                  onChange={e => setEditText(e.target.value)}
                                  maxLength={10000}
                                  className="w-full"
                                />
                                <Button
                                  disabled={busy}
                                  onClick={() =>
                                    void perform(async () => {
                                      await api(`${base}/${a.id}`, 'PATCH', { note: editText })
                                      setEditing('')
                                      await reload()
                                    })
                                  }
                                  type="button"
                                  variant="primary"
                                >
                                  保存修改
                                </Button>
                                <Button
                                  className="quiet"
                                  onClick={() => setEditing('')}
                                  type="button"
                                  variant="quiet"
                                >
                                  取消
                                </Button>
                              </>
                            ) : (
                              <>
                                <p className="m-0 leading-relaxed break-words">{a.note}</p>
                                <Button
                                  className="quiet"
                                  onClick={() => {
                                    setEditing(a.id)
                                    setEditText(a.note)
                                  }}
                                  type="button"
                                  variant="quiet"
                                >
                                  <Pencil size={13} /> 编辑
                                </Button>
                                <Button
                                  className="quiet"
                                  disabled={busy}
                                  onClick={() => {
                                    if (window.confirm('删除这条批注？'))
                                      void perform(async () => {
                                        await api(`${base}/${a.id}`, 'DELETE')
                                        await reload()
                                      })
                                  }}
                                  type="button"
                                  variant="quiet"
                                >
                                  <Trash2 size={13} /> 删除
                                </Button>
                              </>
                            )}
                          </article>
                        ))}
                    </div>
                    {!!annotations.length && (
                      <Button
                        variant="quiet"
                        className="notes-export"
                        onClick={() => {
                          const content = annotations
                            .map(
                              a =>
                                `> ${(a.quote || '').replace(/\n/g, '\n> ')}\n\n${a.note || ''}\n\n— 第 ${a.page} 页`
                            )
                            .join('\n\n---\n\n')
                          const next = [summary.trim(), content].filter(Boolean).join('\n\n---\n\n')
                          if (next.length > 10000) {
                            setError('笔记超过 10000 字，请先整理后再汇总')
                            return
                          }
                          setSummary(next)
                          setNoteView('summary')
                        }}
                      >
                        <FileDown size={14} /> 汇总批注到阅读笔记
                      </Button>
                    )}
                  </div>
                )}
                {noteView === 'saved' && notebookNotes}
                {noteView === 'summary' && (
                  <div className="reading-summary note-document">
                    <div className="note-document-heading">
                      <StickyNote size={16} />
                      <strong>阅读笔记</strong>
                      <span>{summary.length} / 10000</span>
                    </div>
                    {recovered && recovered !== summary && (
                      <Button
                        className="quiet"
                        onClick={() => {
                          setSummary(recovered)
                          setRecovered('')
                        }}
                        type="button"
                        variant="quiet"
                      >
                        恢复未保存的笔记草稿
                      </Button>
                    )}
                    <label className="fastui-field">
                      <TextArea
                        aria-label="阅读笔记"
                        value={summary}
                        onChange={e => setSummary(e.target.value)}
                        maxLength={10000}
                        rows={14}
                        placeholder="记录阅读笔记…"
                        className="w-full"
                      />
                    </label>
                    <Button
                      disabled={busy}
                      onClick={() =>
                        void perform(async () => {
                          await api(`/papers/${paper.id}/summary`, 'PUT', { content: summary })
                          summarySaved.current = summary
                          onSaved(summary)
                          localStorage.removeItem(draftKey)
                          setRecovered('')
                          setStatus('阅读笔记已保存')
                        })
                      }
                      type="button"
                      variant="primary"
                    >
                      保存笔记
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
      {error && (
        <Alert tone="danger" className="reader-feedback">
          {error}
        </Alert>
      )}
      {status && (
        <Alert tone="success" className="reader-feedback">
          {status}
        </Alert>
      )}
    </div>
  )
}
