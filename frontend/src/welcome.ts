import { store } from './storage.ts'

// Whether Patch's welcome banner shows on the dashboard (DESIGN.md §5.8, §11). The banner's ✕ turns it off, the
// Settings switch turns it on or off. Remembered in this browser (`helloHidden`); with storage blocked, the last
// choice is kept in memory, so it still holds for this session.
let session: boolean | null = null

export function welcomeShown(): boolean {
  return session ?? store.get('helloHidden') !== '1'
}

export function setWelcomeShown(shown: boolean): void {
  session = shown
  store.set('helloHidden', shown ? '0' : '1')
}
