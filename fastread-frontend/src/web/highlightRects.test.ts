import { describe, expect, it } from 'vitest'
import { mergeHighlightRects } from './highlightRects'

describe('PDF highlight rectangles', () => {
  it('joins duplicate and adjacent browser fragments into one line', () => {
    const r = { x: .1, y: .2, width: .1, height: .02 }
    const result = mergeHighlightRects([r, { ...r }, { ...r, x: .2005 }])
    expect(result).toHaveLength(1)
    expect(result[0].x).toBe(.1)
    expect(result[0].width).toBeCloseTo(.2005)
    expect(r.width).toBe(.1)
  })
  it('keeps separate lines and columns separate', () => {
    const rects = [
      { x: .1, y: .2, width: .3, height: .02 },
      { x: .55, y: .2, width: .3, height: .02 },
      { x: .1, y: .23, width: .3, height: .02 },
    ]
    expect(mergeHighlightRects(rects)).toEqual(rects)
  })
  it('ignores empty or malformed boxes from a text layer', () => {
    expect(mergeHighlightRects([
      { x: .1, y: .2, width: 0, height: .02 },
      { x: NaN, y: .2, width: .1, height: .02 },
    ])).toEqual([])
  })
})
