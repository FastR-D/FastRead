import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const layoutSource = readFileSync(new URL('./SettingLayout.tsx', import.meta.url), 'utf8')
const pageSource = readFileSync(new URL('../pages/SettingPage/index.tsx', import.meta.url), 'utf8')

describe('settings viewport and scrolling layout', () => {
  it('establishes a definite viewport height below the globally locked document', () => {
    expect(pageSource).toContain('h-dvh min-h-0 w-full overflow-hidden')
    expect(layoutSource).toContain('h-full min-h-0 w-full overflow-hidden')
    expect(layoutSource).toContain('min-h-0 min-w-0 flex-1 overflow-hidden')
  })

  it('keeps the settings navigation usable on narrow and short screens', () => {
    expect(layoutSource).toContain('flex-col md:flex-row')
    expect(layoutSource).toContain('max-h-[40dvh] w-full')
    expect(layoutSource).toContain('md:h-full md:max-h-none md:w-[260px]')
    expect(layoutSource).toContain('min-h-0 flex-1 overflow-y-auto overscroll-contain')
  })
})
