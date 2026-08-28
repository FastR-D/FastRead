import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./ReadingReportView.tsx', import.meta.url), 'utf8')

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
})
