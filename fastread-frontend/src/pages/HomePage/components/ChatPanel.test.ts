import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./ChatPanel.tsx', import.meta.url), 'utf8')

describe('chat bubble rendering contract', () => {
  it('uses the supported messageRender property', () => {
    expect(source).toContain('messageRender:')
    expect(source).not.toContain('contentRender:')
  })

  it('shows structured grounding failures instead of one generic message', () => {
    for (const status of ['retrieval_miss', 'requested_page_missing', 'citation_missing', 'citation_rejected', 'insufficient_source']) {
      expect(source).toContain(status)
    }
    expect(source).toContain('groundingDetail: res.grounding_detail')
    expect(source).toContain('<GroundingNotice')
  })

  it('does not leave a disabled vector index looking busy', () => {
    expect(source).toContain("indexStatus === 'disabled' ? '部署未启用'")
    expect(source).toContain("disabled={indexStatus === 'indexing' || indexStatus === 'disabled'}")
    expect(source).toContain('setIndexStatus(result.status)')
    expect(source).toContain('setIndexPollNonce(value => value + 1)')
  })

  it('starts an available vector index in the background without blocking chat', () => {
    expect(source).toContain("if (res.status === 'idle')")
    expect(source).toContain('const started = await indexTask(taskId)')
    expect(source).toContain("if (started.status === 'indexing') timer = setTimeout(poll, 2000)")
    expect(source).toContain('基础检索仍可使用')
    expect(source).toContain('首次会下载约 0.22 GB 模型')
  })

  it('explains that report conclusions and anaphoric follow-ups are supported', () => {
    expect(source).toContain('可以问原文或阅读报告')
    expect(source).toContain('它在哪几页、为什么')
    expect(source).toContain('这个结论依据哪几页')
  })
})
