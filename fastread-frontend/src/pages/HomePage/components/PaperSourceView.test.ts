import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./PaperSourceView.tsx', import.meta.url), 'utf8')

describe('paper source reading layout', () => {
  it('gives the reader explicit page navigation and collapsible side panels', () => {
    expect(source).toContain('aria-label="上一页"')
    expect(source).toContain('aria-label="下一页"')
    expect(source).toContain("const [pagesOpen, setPagesOpen] = useState(false)")
    expect(source).toContain("const [annotationsOpen, setAnnotationsOpen] = useState(false)")
  })

  it('does not render extracted PDF line breaks as forced visual line breaks', () => {
    expect(source).toContain('whitespace-normal break-normal')
    expect(source).not.toContain('whitespace-pre-wrap break-words')
  })

  it('removes repeated PDF headers from page summaries', () => {
    expect(source).toContain('lineCounts')
    expect(source).toContain('published as')
    expect(source).toContain('pageSummaries.get(page.page)')
  })

  it('keeps figures, tables, formulas, and page layout available through the original PDF', () => {
    expect(source).toContain('原版页（含图表）')
    expect(source).toContain('保留论文中的图、表、公式和版式')
    expect(source).toContain('该视图来自 PDF 文本抽取，不包含图表像素与原始排版')
    expect(source).toContain('<iframe')
    expect(source).toContain("setSourceMode('text')")
  })
})
