import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./SearchConnections.tsx', import.meta.url), 'utf8')

describe('academic search connection settings', () => {
  it('does not hard-code one developer proxy port', () => {
    expect(source).toContain('代理端口以你的客户端设置为准')
    expect(source).not.toContain('127.0.0.1:7897')
  })

  it('explains proxy boundaries and keeps the secret unreadable', () => {
    for (const copy of ['PAPER_SEARCH_PROXY_URL', 'GOOGLE_SCHOLAR_API_URL', 'SERPAPI_API_KEY', 'ELASTICSEARCH_URL', '不要直连', '绝不回显']) {
      expect(source).toContain(copy)
    }
    expect(source).toContain('type="password"')
  })
})
