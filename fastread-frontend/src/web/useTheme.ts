import { useEffect, useLayoutEffect, useState } from 'react'

type Theme = 'light' | 'dark'
const storageKey = 'fastread:web-theme'
const systemQuery = '(prefers-color-scheme: dark)'

function readPreference(): Theme | null {
  try {
    const value = localStorage.getItem(storageKey)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

export function useTheme() {
  const [preference, setPreference] = useState(readPreference)
  const [systemDark, setSystemDark] = useState(() => window.matchMedia(systemQuery).matches)
  const theme = preference || (systemDark ? 'dark' : 'light')

  useLayoutEffect(() => {
    const root = document.documentElement
    root.dataset.theme = theme
    root.style.colorScheme = theme
    root.style.backgroundColor = theme === 'dark' ? '#171c19' : '#fafbf8'
    root.style.color = theme === 'dark' ? '#e4e9e3' : '#262b29'
  }, [theme])

  useEffect(() => {
    const media = window.matchMedia(systemQuery)
    const onSystemChange = () => setSystemDark(media.matches)
    const onStorage = (event: StorageEvent) => {
      if (event.key === storageKey || event.key === null) setPreference(readPreference())
    }
    onSystemChange()
    media.addEventListener('change', onSystemChange)
    window.addEventListener('storage', onStorage)
    return () => {
      media.removeEventListener('change', onSystemChange)
      window.removeEventListener('storage', onStorage)
    }
  }, [])

  function selectTheme(next: Theme) {
    setPreference(next)
    try {
      localStorage.setItem(storageKey, next)
    } catch {
      // The selection still works for this tab when storage is unavailable.
    }
  }

  return { theme, selectTheme }
}
