import { useEffect, useRef, useState } from 'react'

type Outline = { title: string; page: number; depth: number }
type Match = { page: number; occurrence: number }
export function usePdfNavigation(document: any, setPage: (page: number) => void) {
  const [tool, setTool] = useState<'find' | 'outline' | null>(null)
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState<Match[]>([])
  const [active, setActive] = useState(-1)
  const [searching, setSearching] = useState(false)
  const [outline, setOutline] = useState<Outline[]>([])
  const [error, setError] = useState('')
  const index = useRef<{ document: any; pages: string[] }>({ document: null, pages: [] })
  useEffect(() => {
    let dead = false
    setOutline([])
    setQuery('')
    setError('')
    index.current = { document, pages: [] }
    if (document)
      void (async () => {
        const result: Outline[] = []
        async function walk(items: any[], depth: number) {
          for (const item of items) {
            const dest =
              typeof item.dest === 'string' ? await document.getDestination(item.dest) : item.dest
            if (dest?.length) {
              const number =
                typeof dest[0] === 'number' ? dest[0] : await document.getPageIndex(dest[0])
              result.push({ title: item.title, page: number + 1, depth })
            }
            await walk(item.items || [], depth + 1)
          }
        }
        await walk((await document.getOutline()) || [], 0)
        if (!dead) setOutline(result)
      })().catch(() => {
        if (!dead) setError('无法读取文档目录')
      })
    return () => {
      dead = true
    }
  }, [document])
  useEffect(() => {
    let dead = false
    setMatches([])
    setActive(-1)
    const needle = query.replace(/\s/g, '').toLowerCase()
    setSearching(!!document && !!needle)
    if (!document || !needle) return
    const cache = index.current
    const timeout = window.setTimeout(() => {
      void (async () => {
        const found: Match[] = []
        for (let page = 1; page <= document.numPages; page++) {
          if (dead) return
          if (cache.pages[page] === undefined) {
            const content = await (await document.getPage(page)).getTextContent()
            cache.pages[page] = content.items
              .map((item: any) => item.str || '')
              .join('')
              .replace(/\s/g, '')
              .toLowerCase()
          }
          let from = 0,
            occurrence = 0,
            offset: number
          while ((offset = cache.pages[page].indexOf(needle, from)) >= 0) {
            found.push({ page, occurrence: occurrence++ })
            from = offset + needle.length
          }
        }
        if (!dead) {
          setMatches(found)
          if (found.length) {
            setActive(0)
            setPage(found[0].page)
          }
          setSearching(false)
        }
      })().catch(() => {
        if (!dead) {
          setSearching(false)
          setError('文内查找失败，请重新输入')
        }
      })
    }, 250)
    return () => {
      dead = true
      window.clearTimeout(timeout)
    }
  }, [document, query, setPage])
  function move(direction: number) {
    if (!matches.length) return
    const next = (active + direction + matches.length) % matches.length
    setActive(next)
    setPage(matches[next].page)
  }
  return {
    tool,
    setTool,
    query,
    setQuery,
    matches,
    active,
    searching,
    outline,
    error,
    move,
    hit: active >= 0 ? { ...matches[active], quote: query, nonce: active } : null,
  }
}
