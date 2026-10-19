import { API_BASE, assetUrl } from './urls'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { mergeHighlightRects } from './highlightRects'

type Row = Record<string, any>
type Props = { paper: Row; version: string; page: number; setPage: (p: number) => void; api: any; summary: string; setSummary: (s: string) => void; onSaved: (s: string) => void; companion?: ReactNode; companionHeader?: ReactNode; pane?: string; onPane?: (s: string) => void; onQuote?: (selection: Row) => void; citation?: Row | null; notebookNotes?: ReactNode }
let engine: Promise<any> | undefined
let worker: any
function pdfEngine() {
  const url = assetUrl('vendor/pdfjs/pdf.js?v=4.10.38')
  return engine ||= import(/* @vite-ignore */ url).then(pdf => {
    pdf.GlobalWorkerOptions.workerSrc = assetUrl('vendor/pdfjs/pdf.worker.js?v=4.10.38')
    return pdf
  }).catch(error => { engine = undefined; throw error })
}

export default function PdfReader({ paper, version, page, setPage, api, summary, setSummary, onSaved, companion, companionHeader, pane = "notes", onPane, onQuote, citation, notebookNotes }: Props) {
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
  async function reload() { setAnnotations((await api(`${base}?version=${encodeURIComponent(version)}`)).items) }
  async function perform(fn: () => Promise<void>) {
    setError(''); setBusy(true)
    try { await fn() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  useEffect(() => {
    const observer = new ResizeObserver(entries => setWidth(Math.max(200, entries[0].contentRect.width - 32)))
    if (host.current) observer.observe(host.current)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    let dead = false, task: any
    setDocument(null); setReady(false); setError(''); setAnnotations([])
    pdfEngine().then(pdf => {
      if (dead) return
      worker ||= new pdf.PDFWorker()
      task = pdf.getDocument({ url: file, worker, disableStream: true, disableAutoFetch: true, rangeChunkSize: 65536, cMapUrl: assetUrl('vendor/pdfjs/cmaps/'), cMapPacked: true, standardFontDataUrl: assetUrl('vendor/pdfjs/standard_fonts/') })
      return task.promise.then((doc: any) => { if (!dead) setDocument(doc) })
    }).catch(e => { if (!dead) setError(`PDF 加载失败：${e.message}`) })
    api(`${base}?version=${encodeURIComponent(version)}`).then((r: Row) => { if (!dead) setAnnotations(r.items) }).catch((e: Error) => { if (!dead) setError(e.message) })
    return () => { dead = true; void task?.destroy() }
  }, [paper.id, version])
  useEffect(() => {
    setStatus(''); setEditing('')
    try { const draft = JSON.parse(localStorage.getItem(annotationDraftKey) || '{}'); setNote(draft.note || ''); setSelection(draft.selection || null) } catch { setNote(''); setSelection(null) }
  }, [annotationDraftKey])
  function changeNote(value: string) { setNote(value); localStorage.setItem(annotationDraftKey, JSON.stringify({ note: value, selection })) }
  function clearSelection() {
    setSelection(null)
    window.getSelection()?.removeAllRanges()
    localStorage.setItem(annotationDraftKey, JSON.stringify({ note }))
  }
  useEffect(() => {
    if (!document) return
    let dead = false, render: any, layer: any
    setReady(false)
    Promise.all([document.getPage(page), pdfEngine()]).then(async ([p, pdf]) => {
      if (dead || !canvas.current || !text.current) return
      const scale = width / p.getViewport({ scale: 1 }).width * zoom
      const viewport = p.getViewport({ scale })
      setSize({ width: viewport.width, height: viewport.height })
      const ratio = window.devicePixelRatio || 1
      const element = canvas.current
      element.width = Math.floor(viewport.width * ratio); element.height = Math.floor(viewport.height * ratio)
      element.style.width = `${viewport.width}px`; element.style.height = `${viewport.height}px`
      text.current.replaceChildren()
      text.current.style.setProperty('--scale-factor', String(scale))
      render = p.render({ canvasContext: element.getContext('2d'), viewport, transform: [ratio, 0, 0, ratio, 0, 0] })
      await render.promise
      if (dead) return
      layer = new pdf.TextLayer({ textContentSource: p.streamTextContent(), container: text.current, viewport })
      await layer.render()
      if (!dead) setReady(true)
    }).catch(e => { if (!dead && e.name !== 'RenderingCancelledException') setError(`页面渲染失败：${e.message}`) })
    return () => { dead = true; render?.cancel(); layer?.cancel() }
  }, [document, page, width, zoom])
  useEffect(() => {
    if (summary !== summarySaved.current) localStorage.setItem(draftKey, summary)
    const warn = (e: BeforeUnloadEvent) => { if (summary !== summarySaved.current) { e.preventDefault(); e.returnValue = '' } }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [summary, draftKey])
  useEffect(() => {
    setCitationRects([]); setCitationMissing(false)
    if (!ready || !citation?.quote || !text.current || !surface.current) return
    const walker = window.document.createTreeWalker(text.current, NodeFilter.SHOW_TEXT)
    const positions: { node: Node; offset: number }[] = []; let normalized = ''; let node: Node | null
    while ((node = walker.nextNode())) {
      const value = node.textContent || ''
      for (let i = 0; i < value.length; i++) if (!/\s/.test(value[i])) { normalized += value[i].toLowerCase(); positions.push({ node, offset: i }) }
    }
    const needle = String(citation.quote).replace(/\s/g, '').toLowerCase()
    const start = normalized.indexOf(needle)
    if (start < 0 || !needle) { setCitationMissing(true); return }
    const range = window.document.createRange(), first = positions[start], last = positions[start + needle.length - 1]
    range.setStart(first.node, first.offset); range.setEnd(last.node, last.offset + 1)
    const bounds = surface.current.getBoundingClientRect()
    const rects = Array.from(range.getClientRects()).filter(r => r.width > 0 && r.height > 0).map(r => ({ x: (r.left - bounds.left) / bounds.width, y: (r.top - bounds.top) / bounds.height, width: r.width / bounds.width, height: r.height / bounds.height }))
    setCitationRects(rects)
    if (host.current && rects[0]) host.current.scrollTop = Math.max(0, rects[0].y * bounds.height - 80)
  }, [ready, citation, page, size.width])
  function capture() {
    const s = window.getSelection()
    if (!ready || !s?.rangeCount || s.isCollapsed || !text.current?.contains(s.anchorNode) || !text.current?.contains(s.focusNode)) return
    const quote = s.toString().trim()
    if (!quote || !surface.current) return
    const bounds = surface.current.getBoundingClientRect()
    const rects = Array.from(s.getRangeAt(0).getClientRects()).filter(r => r.width > 1 && r.height > 1).slice(0, 200).map(r => {
      const x = Math.max(0, (r.left - bounds.left) / bounds.width), y = Math.max(0, (r.top - bounds.top) / bounds.height)
      return { x, y, width: Math.min(1 - x, r.width / bounds.width), height: Math.min(1 - y, r.height / bounds.height) }
    }).filter(r => r.width > 0 && r.height > 0)
    const picked = { quote, rects: mergeHighlightRects(rects), page }
    setSelection(picked); setNotesOpen(true)
    localStorage.setItem(annotationDraftKey, JSON.stringify({ note, selection: picked }))
  }
  return <div className={`pdf-workspace ${notesOpen ? '' : 'notes-hidden'}`}>
    <div className="pdf-column">
      <div className="pdf-toolbar"><button className="quiet" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button><label>页码<input aria-label="PDF 页码" type="number" min={1} max={document?.numPages || 1} value={page} onChange={e => setPage(Math.max(1, Math.min(document?.numPages || 1, Number(e.target.value) || 1)))} /></label><span>/ {document?.numPages || '…'}</span><button className="quiet" disabled={!document || page >= document.numPages} onClick={() => setPage(page + 1)}>下一页</button><select aria-label="PDF 缩放" value={zoom} onChange={e => setZoom(Number(e.target.value))}><option value={1}>适合宽度</option><option value={1.25}>125%</option><option value={1.5}>150%</option><option value={2}>200%</option></select><button className="quiet" aria-expanded={notesOpen} onClick={() => setNotesOpen(!notesOpen)}>{notesOpen ? '收起右侧' : '展开右侧'}</button><a href={file} target="_blank" rel="noreferrer">原文件</a></div>
      {selection && onQuote && <div className="selection-actions"><span>已选原文</span><button onClick={() => { onQuote({ ...selection, paper_id: paper.id, version_id: version }); setNotesOpen(true) }}>问这段</button><button className="quiet" onClick={() => { onPane?.('notes'); setNotesOpen(true) }}>添加批注</button><button className="quiet" onClick={clearSelection}>取消</button></div>}
      {citationMissing && <p className="citation-fallback">已定位到第 {page} 页，当前版面未能逐字高亮。请对照右侧引文。</p>}
      <div className="pdf-scroll" ref={host}>
        {!ready && <p className="pdf-loading" role="status">{document ? `正在显示第 ${page} 页…` : '正在载入 PDF…'}</p>}
        <div className="pdf-sheet" ref={surface} style={{ width: size.width, height: size.height, visibility: ready ? 'visible' : 'hidden' }} onMouseUp={capture} onTouchEnd={() => window.setTimeout(capture, 100)}>
          <canvas ref={canvas} aria-label={`PDF 第 ${page} 页`} /><div ref={text} className="textLayer" />
          <div className="citation-highlights">{citationRects.map((r, i) => <mark key={i} style={{ left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.width * 100}%`, height: `${r.height * 100}%` }} />)}</div>
          <div className="annotation-highlights">{annotations.filter(a => a.page === page).flatMap(a => mergeHighlightRects(a.rects).map((r, i) => <mark key={`${a.id}:${i}`} title={a.note || a.quote} style={{ left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.width * 100}%`, height: `${r.height * 100}%` }} />))}</div>
        </div>
      </div>
    </div>
    {notesOpen && <div className="reading-notes">{companionHeader}{pane !== "notes" ? companion : <><div className="section-heading"><h2>批注与笔记</h2><span>第 {page} 页</span></div><p className="muted">在 PDF 上选中文字即可批注，也可以直接记下这一页的想法。</p>
      <form onSubmit={e => { e.preventDefault(); void perform(async () => { await api(base, 'POST', { version_id: version, page: selection?.page || page, quote: selection?.quote || '', rects: selection?.rects || [], note }); setSelection(null); window.getSelection()?.removeAllRanges(); setNote(''); localStorage.removeItem(annotationDraftKey); await reload(); setStatus('批注已保存') }) }}>
        {selection && <div className="annotation-selection"><div className="annotation-selection-header"><span>选中原文 · 第 {selection.page} 页</span><button type="button" className="quiet" onClick={clearSelection}>取消选文</button></div><blockquote>{selection.quote}</blockquote></div>}
        <label>当前页批注<textarea aria-label="当前页批注" value={note} onChange={e => changeNote(e.target.value)} maxLength={10000} rows={3} placeholder="这段话的含义、疑问或你的想法…" /></label><button disabled={busy || (!note.trim() && !selection)}>保存批注</button>
      </form>
      <div className="annotation-list">{annotations.map(a => <article key={a.id} className={a.page === page ? 'current-page-note' : ''}><button className="page-link" onClick={() => setPage(a.page)}>第 {a.page} 页</button>{a.quote && <blockquote>{a.quote}</blockquote>}{editing === a.id ? <><textarea aria-label="编辑批注" value={editText} onChange={e => setEditText(e.target.value)} maxLength={10000} /><button disabled={busy} onClick={() => void perform(async () => { await api(`${base}/${a.id}`, 'PATCH', { note: editText }); setEditing(''); await reload() })}>保存修改</button><button className="quiet" onClick={() => setEditing('')}>取消</button></> : <><p>{a.note}</p><button className="quiet" onClick={() => { setEditing(a.id); setEditText(a.note) }}>编辑</button><button className="quiet" disabled={busy} onClick={() => { if (window.confirm('删除这条批注？')) void perform(async () => { await api(`${base}/${a.id}`, 'DELETE'); await reload() }) }}>删除</button></>}</article>)}</div>
      {notebookNotes}<div className="reading-summary"><h2>阅读笔记</h2>{recovered && recovered !== summary && <button className="quiet" onClick={() => { setSummary(recovered); setRecovered('') }}>恢复未保存的笔记草稿</button>}<label>整篇论文的理解<textarea aria-label="阅读笔记" value={summary} onChange={e => setSummary(e.target.value)} maxLength={10000} rows={8} placeholder="边读边整理你的理解…" /></label><button disabled={busy} onClick={() => void perform(async () => { await api(`/papers/${paper.id}/summary`, 'PUT', { content: summary }); summarySaved.current = summary; onSaved(summary); localStorage.removeItem(draftKey); setRecovered(''); setStatus('阅读笔记已保存') })}>保存笔记</button><small>原有个人总结保留在这里。草稿暂存本机，保存后可在其他设备继续阅读。</small></div>
    </>}</div>}
    {error && <p className="error reader-feedback" role="alert">{error}</p>}{status && <p className="notice reader-feedback" role="status">{status}</p>}
  </div>
}
