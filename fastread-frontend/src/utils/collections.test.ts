import { describe, expect, it } from 'vitest'
import {
  mergeCollectionFolders,
  normalizeCollectionFolder,
  validateCollectionFolder,
} from './collections'

describe('collection folder names', () => {
  it('normalizes unicode and whitespace while preserving a human-readable name', () => {
    expect(normalizeCollectionFolder('  AI\t  Safety  ')).toBe('AI Safety')
    expect(normalizeCollectionFolder('ＡＩ')).toBe('ＡＩ')
  })

  it('rejects empty and overlong names', () => {
    expect(validateCollectionFolder(' \n ')).toBe('收藏夹名称不能为空')
    expect(validateCollectionFolder('a'.repeat(81))).toContain('80')
  })

  it('merges registered and task-derived folders without case-only duplicates', () => {
    expect(mergeCollectionFolders(['AI Safety', '空目录'], ['ai safety', '组会'])).toEqual([
      '默认收藏夹',
      '空目录',
      '组会',
      'AI Safety',
    ])
  })
})
