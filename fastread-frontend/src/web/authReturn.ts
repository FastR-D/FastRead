const key = 'fastread.cas.destination'
const allowed = ['paper', 'book', 'section', 'pending', 'url', 'source']

export function rememberCASDestination() {
  const query = new URLSearchParams(window.location.search)
  const parameters = Object.fromEntries(
    allowed.flatMap(name => (query.has(name) ? [[name, query.get(name)!]] : []))
  )
  try {
    sessionStorage.setItem(key, JSON.stringify({ parameters, created: Date.now() }))
  } catch {
    /* Login remains available without storage. */
  }
}

export function arrivalParameters() {
  const query = new URLSearchParams(window.location.search)
  if (query.get('fastcas') !== 'complete') return query
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) || 'null')
    if (
      saved &&
      typeof saved.created === 'number' &&
      Date.now() - saved.created >= 0 &&
      Date.now() - saved.created < 600_000
    ) {
      for (const name of allowed) {
        const value = saved.parameters?.[name]
        if (!query.has(name) && typeof value === 'string' && value.length <= 2048)
          query.set(name, value)
      }
    }
  } catch {
    /* Ignore malformed or unavailable storage. */
  }
  return query
}

export function clearCASDestination() {
  try {
    sessionStorage.removeItem(key)
  } catch {
    /* Optional tab-local state. */
  }
}
