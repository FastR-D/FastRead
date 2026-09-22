import { useEffect, useState } from 'react'

export type WorkspaceRoute = {
  view: 'library' | 'books' | 'notes' | 'archive' | 'discover'
  paper?: string
  book?: string
  page?: number
  version?: string
  q?: string
  tag?: string
  offset?: number
}

export function parseRoute(search: string): WorkspaceRoute {
  const params = new URLSearchParams(search)
  const view = params.get('view')
  return {
    view: ['books', 'notes', 'archive', 'discover'].includes(view || '')
      ? (view as WorkspaceRoute['view'])
      : 'library',
    paper: params.get('paper') || undefined,
    book: params.get('book') || undefined,
    page:
      params.has('page') && Number.isFinite(Number(params.get('page')))
        ? Math.max(1, Math.floor(Number(params.get('page')) || 1))
        : undefined,
    version: params.get('version') || undefined,
    q: params.get('q') || '',
    tag: params.get('tag') || '',
    offset: Number.isFinite(Number(params.get('offset')))
      ? Math.max(0, Math.floor(Number(params.get('offset')) || 0))
      : 0,
  }
}

export function routeUrl(route: WorkspaceRoute) {
  const params = new URLSearchParams()
  if (route.view !== 'library') params.set('view', route.view)
  for (const key of ['paper', 'book', 'version', 'q', 'tag'] as const) {
    if (route[key]) params.set(key, route[key])
  }
  if (route.page) params.set('page', String(route.page))
  if (route.offset) params.set('offset', String(route.offset))
  return `/${params.size ? `?${params}` : ''}`
}

export function useWorkspaceRoute() {
  const [route, setRoute] = useState(() => parseRoute(window.location.search))
  useEffect(() => {
    const onPop = () => setRoute(parseRoute(window.location.search))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])
  function navigate(next: WorkspaceRoute, replace = false) {
    const url = routeUrl(next)
    if (url !== `${window.location.pathname}${window.location.search}`) {
      window.history[replace ? 'replaceState' : 'pushState'](null, '', url)
    }
    setRoute(next)
  }
  return [route, navigate] as const
}
