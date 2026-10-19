import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

describe('PDF reader asset URLs', () => {
  it('does not expose root-relative vendor literals to the FastResearch /read proxy', () => {
    const source = readFileSync(new URL('./PdfReader.tsx', import.meta.url), 'utf8')

    expect(source).not.toMatch(/assetUrl\(['"]\/vendor\//)
  })
})
