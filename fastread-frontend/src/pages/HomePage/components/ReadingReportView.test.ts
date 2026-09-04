import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./ReadingReportView.tsx', import.meta.url), 'utf8')
const noteService = readFileSync(new URL('../../../services/note.ts', import.meta.url), 'utf8')

describe('academic identity gate disclosure', () => {
  it('treats security, systems, and AI conferences as the shared core gate', () => {
    expect(source).toContain('安全、系统或 AI 核心顶会')
    expect(source).toContain('论文内声明已展示，仍需官方会议记录闭合正式身份')
    expect(source).not.toContain('未通过四大安全顶会正式论文 Gate')
  })

  it('keeps the personal summary visible and exposes deterministic markdown export', () => {
    expect(source).toContain('我的总结')
    expect(source).toContain('导出 Markdown')
    expect(source).toContain('get_reading_report_markdown_url(task.id)')
    expect(source).not.toContain('写 300 字总结')
  })

  it('discloses the model context used for a generated report', () => {
    expect(source).toContain('generation_provenance?.context_policy')
    expect(source).toContain('included_page_count')
    expect(source).toContain('context_characters.toLocaleString()')
    expect(source).toContain('通读更长的分页正文')
    expect(source).toContain("item.evidence?.length ? <EvidenceQuotes")
    expect(source).toContain("item.page_start || 'page'")
  })

  it('allows long grounded reports to finish and reports failures explicitly', () => {
    expect(noteService).toContain("timeout: 600000")
    expect(source).toContain('正在通读全文并校验页码，请耐心等待…')
    expect(source).toContain("console.error('关键问题阅读报告生成失败'")
  })
})
