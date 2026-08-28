import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./index.tsx', import.meta.url), 'utf8')

describe('library collection navigation', () => {
  it('keeps folder and tag filters visible in the primary library', () => {
    for (const copy of ['收藏目录', '全部收藏夹', '全部标签', '收藏夹与标签']) {
      expect(source).toContain(copy)
    }
  })

  it('shows save, error, and retry states instead of console-only failure', () => {
    for (const copy of ['立即保存', "collectionState?.status === 'error'", '重试']) {
      expect(source).toContain(copy)
    }
  })
})

