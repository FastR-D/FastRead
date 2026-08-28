import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const visibleProductSources = [
  './Onboarding/index.tsx',
  './LibraryPage/index.tsx',
  '../layouts/HomeLayout.tsx',
  './SettingPage/about.tsx',
].map(path => readFileSync(new URL(path, import.meta.url), 'utf8'))

describe('personal summary product copy', () => {
  it('does not promise a fixed 300-character summary', () => {
    for (const source of visibleProductSources) {
      expect(source).toContain('个人总结')
      expect(source).not.toMatch(/300\s*字/)
    }
  })
})
