import { useEffect, useState } from 'react'
import { store } from './storage.ts'

export type Theme = 'light' | 'dark'

// index.html's inline script has already picked the start theme (URL, then saved, then system) before the
// first paint; React starts from what it set, so there is one rule in one place.
function startTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

/** The light/dark switch: sets data-theme on <html> (dark tokens hang off it) and remembers the choice. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(startTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  function toggle() {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    store.set('theme', next) // a saved choice overrides the system from now on
    setTheme(next)
  }

  return [theme, toggle]
}
