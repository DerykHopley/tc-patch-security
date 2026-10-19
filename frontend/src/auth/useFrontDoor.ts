import { useSyncExternalStore } from 'react'
import { clearChat, tabStorage } from '../chat/chatStore.ts'
import { store } from '../storage.ts'
import { frontDoor, type FrontDoor } from './signInView.ts'

// The signed-out screen for the page's address (B42, #80): the landing page, the sign-in screen, or a short wait.
// No Clerk code here, so main.tsx's fallback (before Clerk's chunk loads) uses the same rule as ClerkApp.

/** Re-render on every address change: Clerk's hash routing sets location.hash; the landing page's buttons and Back
 * push or pop history entries. */
export function subscribeToAddress(onChange: () => void) {
  window.addEventListener('hashchange', onChange)
  window.addEventListener('popstate', onChange)
  return () => {
    window.removeEventListener('hashchange', onChange)
    window.removeEventListener('popstate', onChange)
  }
}

/** Remembered per browser (DESIGN.md §11): was this browser signed in when Clerk last answered? Only decides whether
 * to wait for Clerk or show the landing page at once; it never lets anyone in. */
export function rememberSignedIn(signedIn: boolean): void {
  store.set('signedInHere', signedIn ? '1' : '0')
  // B49 C5: signed out (by the menu, the access screens, or a session that ended), the tab forgets the conversation
  if (!signedIn) clearChat(tabStorage())
}

export function useFrontDoor(clerkLoaded: boolean): FrontDoor {
  return useSyncExternalStore(subscribeToAddress, () =>
    frontDoor(window.location, { loaded: clerkLoaded, wasSignedIn: store.get('signedInHere') === '1' }))
}
