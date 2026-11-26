import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import { mergeHighlightRects } from './highlightRects'
import { pdfEngine } from './pdfEngine'
type Row = Record<string, any>
export default function PdfPage({
  document,
  page,
  width,
  zoom,
  host,
  annotations,
  citation,
  onCapture,
  onReady,
  onMeasure,
  force,
}: {
  document: any
  page: number
  width: number
  zoom: number
  host: RefObject<HTMLDivElement | null>
  annotations: Row[]
  citation?: Row | null
  onCapture: (value: Row) => void
  onReady: (page: number) => void
  onMeasure: () => void
  force: boolean
}) {
  const surface = useRef<HTMLDivElement>(null),
    canvas = useRef<HTMLCanvasElement>(null),
    text = useRef<HTMLDivElement>(null)
  const [nearby, setNearby] = useState(false),
    [aspect, setAspect] = useState(842 / 595)
  const visible = nearby || force
  const [ready, setReady] = useState(false),
    [error, setError] = useState('')
  const [citationRects, setCitationRects] = useState<Row[]>([]),
    [citationMissing, setCitationMissing] = useState(false)
  useLayoutEffect(() => {
    onMeasure()
  }, [aspect, onMeasure])
  const size = { width: width * zoom, height: width * zoom * aspect }
  useEffect(() => {
    const observer = new IntersectionObserver(entries => setNearby(entries[0].isIntersecting), {
      root: host.current,
      rootMargin: '900px 0px',
    })
    if (surface.current) observer.observe(surface.current)
    return () => observer.disconnect()
  }, [host])
  useEffect(() => {
    if (ready) onReady(page)
  }, [ready, page, onReady])
  useEffect(() => {
    if (!document || !visible) {
      setReady(false)
      if (canvas.current) {
        canvas.current.width = 0
        canvas.current.height = 0
      }
      text.current?.replaceChildren()
      return
    }
    let dead = false,
      render: any,
      layer: any
    setReady(false)
    setError('')
    Promise.all([document.getPage(page), pdfEngine()])
      .then(async ([p, pdf]) => {
        if (dead || !canvas.current || !text.current) return
        const scale = (width / p.getViewport({ scale: 1 }).width) * zoom
        const viewport = p.getViewport({ scale })
        setAspect(viewport.height / viewport.width)
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
  }, [document, page, width, zoom, visible])
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
    let start = normalized.indexOf(needle)
    for (let i = 0; i < (citation.occurrence || 0) && start >= 0; i++)
      start = normalized.indexOf(needle, start + needle.length)
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
      host.current.scrollTop = Math.max(
        0,
        surface.current.offsetTop + rects[0].y * bounds.height - 80
      )
  }, [ready, citation, page, size.width, host])
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
    onCapture(picked)
  }
  return (
    <div
      className="pdf-sheet relative mx-auto shrink-0"
      ref={surface}
      data-page={page}
      data-ready={ready}
      style={{
        width: size.width,
        height: size.height,
      }}
      onMouseUp={capture}
      onTouchEnd={() => window.setTimeout(capture, 100)}
    >
      {error && (
        <p role="alert" className="pdf-page-message">
          {error}
        </p>
      )}
      {citationMissing && (
        <p role="status" className="pdf-page-message">
          已定位到第 {page} 页，当前版面未能逐字高亮。
        </p>
      )}
      <canvas
        className="block"
        style={{ visibility: ready ? 'visible' : 'hidden' }}
        ref={canvas}
        aria-label={`PDF 第 ${page} 页`}
      />
      {!ready && <span className="pdf-page-placeholder">第 {page} 页</span>}
      <div aria-hidden={!ready} ref={text} className="textLayer" />
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
  )
}
