import { describe, expect, it } from 'vitest'
import { parseRoute, routeUrl } from './navigation'

describe('workspace URLs', () => {
  it('leaves an unspecified page unset so the reader can resume its saved position', () => {
    expect(parseRoute('?paper=p1').page).toBeUndefined()
    expect(parseRoute('?paper=p1&page=3').page).toBe(3)
  })
  it('preserves a citation version and its parent knowledge base in a shared link', () => {
    const route = { view: 'books' as const, book: '研究/1', paper: 'p&2', page: 12, version: 'v?3' }
    expect(parseRoute(routeUrl(route).slice(1))).toMatchObject(route)
  })
  it('keeps search, tag and pagination available after reload or browser back', () => {
    const route = {
      view: 'archive' as const,
      q: 'attention & 检索',
      tag: 'long context',
      offset: 40,
    }
    expect(parseRoute(routeUrl(route).slice(1))).toMatchObject(route)
  })
  it('bounds malformed numbers and rejects unrecognized views', () => {
    expect(parseRoute('?view=unknown&page=-3&offset=Infinity')).toMatchObject({
      view: 'library',
      page: 1,
      offset: 0,
    })
    expect(parseRoute('?page=Infinity').page).toBeUndefined()
  })
})
