import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./ChatPanel.tsx', import.meta.url), 'utf8')

describe('chat bubble rendering contract', () => {
  it('uses the supported messageRender property', () => {
    expect(source).toContain('messageRender:')
    expect(source).not.toContain('contentRender:')
  })
})
