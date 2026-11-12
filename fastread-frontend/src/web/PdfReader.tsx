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
} from '@fastrd/ui-react'
import { API_BASE, assetUrl } from './urls'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { mergeHighlightRects } from './highlightRects'
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
}
let engine: Promise<any> | undefined
let worker: any
function pdfEngine() {
  const url = new URL(assetUrl('/vendor/pdfjs/pdf.js?v=4.10.38'), window.location.origin).href
  return (engine ||= import(/* @vite-ignore */ url)
    .then(pdf => {
      pdf.GlobalWorkerOptions.workerSrc = assetUrl('/vendor/pdfjs/pdf.worker.js?v=4.10.38')
      return pdf
    })
    .catch(error => {
      engine = undefined
      throw error
    }))
}
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
}: Props) {
  const surface = useRef<HTMLDivElement>(null)
  const host = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const text = useRef<HTMLDivElement>(null)
  const [document, setDocument] = useState<any>(null)
  const [width, setWidth] = useState(800)
  const [zoom, setZoom] = useState(1)
  const [size, setSize] = useState({ width: 1, height: 1 })
  const [ready, setReady] = useState(false)
  const [citationRects, setCitationRects] = useState<Row[]>([])
  const [citationMissing, setCitationMissing] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [annotations, setAnnotations] = useState<Row[]>([])
  const [selection, setSelection] = useState<Row | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [notesOpen, setNotesOpen] = useState(true)
  const [editing, setEditing] = useState('')
  const [editText, setEditText] = useState('')
  const summarySaved = useRef(paper.summary || '')
  const draftKey = `notes:${paper.id}`
  const annotationDraftKey = `annotation:${paper.id}:${version}:${page}`
  const [recovered, setRecovered] = useState(() => localStorage.getItem(draftKey) || '')
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
    const observer = new ResizeObserver(entries =>
      setWidth(Math.max(200, entries[0].contentRect.width - 32))
    )
    if (host.current) observer.observe(host.current)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    let dead = false,
      task: any
    setDocument(null)
    setReady(false)
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
    if (!document) return
    let dead = false,
      render: any,
      layer: any
    setReady(false)
    Promise.all([document.getPage(page), pdfEngine()])
      .then(async ([p, pdf]) => {
        if (dead || !canvas.current || !text.current) return
        const scale = (width / p.getViewport({ scale: 1 }).width) * zoom
        const viewport = p.getViewport({ scale })
        setSize({ width: viewport.width, height: viewport.height })
        const ratio = window.devicePixelRatio || 1
        const element = canvas.current
        element.width = Math.floor(viewport.width * ratio)
        element.height = Math.floor(viewport.height * ratio)
        element.style.width = `${viewport.width}px`
        element.style.height = `${viewport.height}px`
        text.current.replaceChildren()
        text.current.style.setProperty('--scale-factor', String(scale))
        render = p.render({
          canvasContext: element.getContext('2d'),
          viewport,
          transform: [ratio, 0, 0, ratio, 0, 0],
        })
        await render.promise
        if (dead) return
        layer = new pdf.TextLayer({
          textContentSource: p.streamTextContent(),
          container: text.current,
          viewport,
        })
        await layer.render()
        if (!dead) setReady(true)
      })
      .catch(e => {
        if (!dead && e.name !== 'RenderingCancelledException')
          setError(`页面渲染失败：${e.message}`)
      })
    return () => {
      dead = true
      render?.cancel()
      layer?.cancel()
    }
  }, [document, page, width, zoom])
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
  useEffect(() => {
    setCitationRects([])
    setCitationMissing(false)
    if (!ready || !citation?.quote || !text.current || !surface.current) return
    const walker = window.document.createTreeWalker(text.current, NodeFilter.SHOW_TEXT)
    const positions: {
      node: Node
      offset: number
    }[] = []
    let normalized = ''
    let node: Node | null
    while ((node = walker.nextNode())) {
      const value = node.textContent || ''
      for (let i = 0; i < value.length; i++)
        if (!/\s/.test(value[i])) {
          normalized += value[i].toLowerCase()
          positions.push({ node, offset: i })
        }
    }
    const needle = String(citation.quote).replace(/\s/g, '').toLowerCase()
    const start = normalized.indexOf(needle)
    if (start < 0 || !needle) {
      setCitationMissing(true)
      return
    }
    const range = window.document.createRange(),
      first = positions[start],
      last = positions[start + needle.length - 1]
    range.setStart(first.node, first.offset)
    range.setEnd(last.node, last.offset + 1)
    const bounds = surface.current.getBoundingClientRect()
    const rects = Array.from(range.getClientRects())
      .filter(r => r.width > 0 && r.height > 0)
      .map(r => ({
        x: (r.left - bounds.left) / bounds.width,
        y: (r.top - bounds.top) / bounds.height,
        width: r.width / bounds.width,
        height: r.height / bounds.height,
      }))
    setCitationRects(rects)
    if (host.current && rects[0])
      host.current.scrollTop = Math.max(0, rects[0].y * bounds.height - 80)
  }, [ready, citation, page, size.width])
  function capture() {
    const s = window.getSelection()
    if (
      !ready ||
      !s?.rangeCount ||
      s.isCollapsed ||
      !text.current?.contains(s.anchorNode) ||
      !text.current?.contains(s.focusNode)
    )
      return
    const quote = s.toString().trim()
    if (!quote || !surface.current) return
    const bounds = surface.current.getBoundingClientRect()
    const rects = Array.from(s.getRangeAt(0).getClientRects())
      .filter(r => r.width > 1 && r.height > 1)
      .slice(0, 200)
      .map(r => {
        const x = Math.max(0, (r.left - bounds.left) / bounds.width),
          y = Math.max(0, (r.top - bounds.top) / bounds.height)
        return {
          x,
          y,
          width: Math.min(1 - x, r.width / bounds.width),
          height: Math.min(1 - y, r.height / bounds.height),
        }
      })
      .filter(r => r.width > 0 && r.height > 0)
    const picked = { quote, rects: mergeHighlightRects(rects), page }
    setSelection(picked)
    setNotesOpen(true)
    localStorage.setItem(annotationDraftKey, JSON.stringify({ note, selection: picked }))
  }
  return (
    <div
      className={`pdf-workspace grid min-h-0 min-w-0 flex-1 grid-cols-1 gap-3 xl:grid-rows-[minmax(0,1fr)] ${notesOpen ? 'xl:grid-cols-[minmax(0,1fr)_22rem]' : 'notes-hidden'}`}
    >
      <div className="pdf-column fastui-section flex min-h-0 min-w-0 flex-col overflow-hidden">
        <Toolbar label="PDF 阅读工具" className="pdf-toolbar shrink-0">
          <Button
            className="quiet"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            type="button"
            variant="quiet"
          >
            上一页
          </Button>
          <label className="fastui-field">
            页码
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
              className="w-16"
            />
          </label>
          <span>/ {document?.numPages || '…'}</span>
          <Button
            className="quiet"
            disabled={!document || page >= document.numPages}
            onClick={() => setPage(page + 1)}
            type="button"
            variant="quiet"
          >
            下一页
          </Button>
          <Select
            aria-label="PDF 缩放"
            value={zoom}
            onChange={e => setZoom(Number(e.target.value))}
            className="w-auto"
          >
            <option value={1}>适合宽度</option>
            <option value={1.25}>125%</option>
            <option value={1.5}>150%</option>
            <option value={2}>200%</option>
          </Select>
          <Button
            className="quiet"
            aria-expanded={notesOpen}
            onClick={() => setNotesOpen(!notesOpen)}
            type="button"
            variant="quiet"
          >
            {notesOpen ? '收起右侧' : '展开右侧'}
          </Button>
          <a href={file} target="_blank" rel="noreferrer" className="fastui-link break-words">
            原文件
          </a>
        </Toolbar>
        {selection && onQuote && (
          <Toolbar label="选文操作" className="selection-actions shrink-0">
            <span>已选原文</span>
            <Button
              onClick={() => {
                onQuote({ ...selection, paper_id: paper.id, version_id: version })
                setNotesOpen(true)
              }}
              type="button"
              variant="primary"
            >
              问这段
            </Button>
            <Button
              className="quiet"
              onClick={() => {
                onPane?.('notes')
                setNotesOpen(true)
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
        {citationMissing && (
          <Alert tone="warning" className="shrink-0">
            已定位到第 {page} 页，当前版面未能逐字高亮。请对照右侧引文。
          </Alert>
        )}
        <CanvasSurface
          grid={false}
          role="region"
          aria-label="PDF 原文"
          tabIndex={0}
          className="pdf-scroll relative h-[60dvh] min-w-0 overflow-auto p-4 xl:h-auto xl:min-h-0 xl:flex-1"
          ref={host}
        >
          {!ready && <Loading label={document ? `正在显示第 ${page} 页…` : '正在载入 PDF…'} />}
          <div
            className="pdf-sheet relative mx-auto shrink-0"
            ref={surface}
            style={{
              width: size.width,
              height: size.height,
              visibility: ready ? 'visible' : 'hidden',
            }}
            onMouseUp={capture}
            onTouchEnd={() => window.setTimeout(capture, 100)}
          >
            <canvas className="block" ref={canvas} aria-label={`PDF 第 ${page} 页`} />
            <div ref={text} className="textLayer" />
            <div className="citation-highlights pointer-events-none absolute inset-0 z-1">
              {citationRects.map((r, i) => (
                <mark
                  className="absolute bg-[var(--fastui-selected)] outline outline-1 outline-[var(--fastui-focus)]"
                  key={i}
                  style={{
                    left: `${r.x * 100}%`,
                    top: `${r.y * 100}%`,
                    width: `${r.width * 100}%`,
                    height: `${r.height * 100}%`,
                  }}
                />
              ))}
            </div>
            <div className="annotation-highlights pointer-events-none absolute inset-0 z-1 opacity-30 mix-blend-multiply">
              {annotations
                .filter(a => a.page === page)
                .flatMap(a =>
                  mergeHighlightRects(a.rects).map((r, i) => (
                    <mark
                      className="absolute bg-[var(--fastui-warning)]"
                      key={`${a.id}:${i}`}
                      title={a.note || a.quote}
                      style={{
                        left: `${r.x * 100}%`,
                        top: `${r.y * 100}%`,
                        width: `${r.width * 100}%`,
                        height: `${r.height * 100}%`,
                      }}
                    />
                  ))
                )}
            </div>
          </div>
        </CanvasSurface>
      </div>
      {notesOpen && (
        <div className="reading-notes fastui-section min-h-0 min-w-0 xl:overflow-auto">
          {companionHeader}
          <div
            className="grid content-start gap-5 p-5"
            id={panelId}
            role={panelId ? 'tabpanel' : undefined}
            aria-labelledby={labelledBy}
          >
            {pane !== 'notes' ? (
              companion
            ) : (
              <>
                <PanelHeader className="section-heading">
                  <h2 className="fastui-heading m-0 text-base">批注</h2>
                  <span>第 {page} 页</span>
                </PanelHeader>
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
                  className="grid min-w-0 gap-4"
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
                    当前页批注
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
                <div className="annotation-list grid gap-3">
                  {annotations.map(a => (
                    <article key={a.id} className={a.page === page ? 'current-page-note' : ''}>
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
                            编辑
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
                            删除
                          </Button>
                        </>
                      )}
                    </article>
                  ))}
                </div>
                {notebookNotes}
                <div className="reading-summary grid gap-3">
                  <h2 className="fastui-heading m-0 text-base">阅读笔记</h2>
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
                    笔记内容
                    <TextArea
                      aria-label="阅读笔记"
                      value={summary}
                      onChange={e => setSummary(e.target.value)}
                      maxLength={10000}
                      rows={8}
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
              </>
            )}
          </div>
        </div>
      )}
      {error && (
        <Alert tone="danger" className="reader-feedback col-span-full">
          {error}
        </Alert>
      )}
      {status && (
        <Alert tone="success" className="reader-feedback col-span-full">
          {status}
        </Alert>
      )}
    </div>
  )
}
