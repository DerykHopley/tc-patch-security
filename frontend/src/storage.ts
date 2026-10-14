// Per-browser conveniences (DESIGN.md §11). Storage can be blocked (private windows, strict settings),
// so every read and write is wrapped: a blocked storage forgets, it never breaks the app.

export type StorageKey = 'theme' | 'sidenavCollapsed'

export const store = {
  get(key: StorageKey): string | null {
    try {
      return localStorage.getItem(key)
    } catch {
      return null
    }
  },
  set(key: StorageKey, value: string): void {
    try {
      localStorage.setItem(key, value)
    } catch {
      // blocked: the choice lasts until the page reloads
    }
  },
}
