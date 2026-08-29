import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./index.tsx', import.meta.url), 'utf8')

describe('paper search disclosure', () => {
  it('shows the expanded core corpus and supplemental sources', () => {
    for (const copy of ['安全四大', '系统顶会', 'AI 顶会', 'ICLR', 'ICML', 'AAAI', 'NeurIPS', 'ACL', 'arXiv', 'OpenAlex', 'Semantic Scholar', 'Google Scholar']) {
      expect(source).toContain(copy)
    }
  })

  it('requires a user-configured proxy and exposes each provider state', () => {
    for (const copy of ['学术检索连接', 'FastRead 不猜测端口', '不会静默直连', '代理已连接 · 来源限流', '本机服务未启动 · 已使用内置索引', '本次检索式']) {
      expect(source).toContain(copy)
    }
  })

  it('shows index time, provider health, and the metadata/full-text boundary', () => {
    for (const copy of ['索引更新', '本次检索', 'Elasticsearch', '发现元数据 · 全文未核验', '导入全文并阅读']) {
      expect(source).toContain(copy)
    }
  })

  it('puts paged results before diagnostics and scrolls them into view', () => {
    expect(source.indexOf('检索结果 ·')).toBeLessThan(source.indexOf('检索来源、时效与证据边界'))
    for (const copy of ['limit: 100', '每页显示数量', '上一页', '下一页', 'scrollIntoView']) {
      expect(source).toContain(copy)
    }
  })
})
