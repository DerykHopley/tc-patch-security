import { useSyncExternalStore } from 'react'
import { clearChat, tabStorage } from '../chat/chatStore.ts'
import { store } from '../storage.ts'
import { frontDoor, rememberedSignIn, SIGNING_IN, type FrontDoor } from './signInView.ts'

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

/** Remembered per browser (DESIGN.md §11): was this browser signed in when Clerk last answered, or on the sign-in
 * form (B51)? Only decides whether to wait for Clerk or show the landing page at once; it never lets anyone in. */
export function rememberSignedIn(signedIn: boolean): void {
  const door = frontDoor(window.location, { loaded: true, signedInHere: null })
  store.set('signedInHere', rememberedSignIn(signedIn, door))
  // B49 C5: signed out (by the menu, the access screens, or a session that ended), the tab forgets the conversation
  if (!signedIn) clearChat(tabStorage())
}

/** The sign-in form is showing (B51, #80): the load of `/` after signing in waits for Clerk, not the landing page.
 * Also on reaching the form from the landing page, where Clerk doesn't answer again. */
export function rememberSigningIn(): void {
  store.set('signedInHere', SIGNING_IN)
}

// Read once, as the page loads: the key speaks for the last visit. Read live, the form's own `pending` would make
// Back from the form to the landing page wait for Clerk too, when Clerk is slow (B51).
const signedInHereAtLoad = store.get('signedInHere')

export function useFrontDoor(clerkLoaded: boolean): FrontDoor {
  return useSyncExternalStore(subscribeToAddress, () =>
    frontDoor(window.location, { loaded: clerkLoaded, signedInHere: signedInHereAtLoad }))
}
