import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('../../public/theme-init.js', import.meta.url), 'utf8')

function boot(saved: string | null, systemDark: boolean, blocked = false) {
  const root = { dataset: {} as Record<string, string>, style: {} as Record<string, string> }
  runInNewContext(source, {
    document: { documentElement: root },
    window: { matchMedia: () => ({ matches: systemDark }) },
    localStorage: {
      getItem() {
        if (blocked) throw new Error('Storage unavailable')
        return saved
      },
    },
  })
  return root
}

describe('appearance before the application loads', () => {
  it.each([
    ['dark', false, 'dark'],
    ['light', true, 'light'],
    [null, true, 'dark'],
    [null, false, 'light'],
    ['invalid', true, 'dark'],
  ] as const)('resolves saved %s with system dark %s to %s', (saved, systemDark, expected) => {
    const root = boot(saved, systemDark)
    expect(root.dataset.theme).toBe(expected)
    expect(root.style.colorScheme).toBe(expected)
    expect(root.style.backgroundColor).toBe(expected === 'dark' ? '#171c19' : '#fafbf8')
  })

  it('can paint the system theme even when preference storage is unavailable', () => {
    expect(boot(null, true, true).dataset.theme).toBe('dark')
  })
})
