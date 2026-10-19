// Sign-in setup (B31, #78; open sign-up B38, #81): Clerk stays inside Patch, and the sign-in screen picks its view
// from the address.
//
// Clerk's checks are in docs/SOURCE-CHECKS.md (Clerk, B31 and B38). In short: without signInUrl and signUpUrl,
// Clerk's components send a sign-up (an SSO account it doesn't know) to the instance's hosted Account Portal. So every
// URL Clerk gets is a path on this page. `<SignIn withSignUp>` then runs its sign-up steps itself, under `#/create`.
// Sign-up is open (Clerk's Public mode, B38): anyone can make an account there, then asks the owner for access
// (access.ts). No invitations any more.

/** The URLs ClerkProvider gets: all on this page, so no step ever leaves Patch for Clerk's hosted page. Since B42
 * (#80) the landing page is the front door, so the form has its own path; signed in or out, Clerk sends to `/`. */
export const CLERK_URLS = {
  signInUrl: '/sign-in',
  signUpUrl: '/sign-in#/create',
  signInFallbackRedirectUrl: '/',
  signUpFallbackRedirectUrl: '/',
  afterSignOutUrl: '/',
} as const

export type SignInView = 'sign-in' | 'sign-up'

/** Which view the sign-in screen shows at this address (`window.location`'s hash): Clerk's sign-up steps under
 * `#/create`, else sign-in. */
export function signInView({ hash }: { search: string; hash: string }): SignInView {
  const path = hash.replace(/^#/, '').split('?', 1)[0].replace(/\/$/, '')
  return path === '/create' || path.startsWith('/create/') ? 'sign-up' : 'sign-in'
}

/** What a signed-out visitor sees (B42, #80): `landing`, the `sign-in` screen, or `wait` (the "Opening Patch" card
 * while Clerk loads). */
export type FrontDoor = 'landing' | 'sign-in' | 'wait'

export const SIGN_IN_PATH = CLERK_URLS.signInUrl
export const REQUEST_ACCESS_PATH = CLERK_URLS.signUpUrl

/** The screen for a signed-out (or not yet known) visitor at this address. The sign-in form lives at /sign-in, on
 * Clerk's own steps (hash routes, `#/…`, which Clerk may append to any path) and on an old invitation link; every
 * other address, an unknown one too (#96), is the landing page. While Clerk still loads, a browser that was signed
 * in last time, or was on the sign-in form (B51), waits (`wait`), so nobody sees the landing page for a moment before
 * the app. `signedInHere` is the per-browser key (DESIGN.md §11); `rememberedSignIn` gives its values. */
export function frontDoor(
  { pathname, search, hash }: { pathname: string; search: string; hash: string },
  clerk: { loaded: boolean; signedInHere: string | null },
): FrontDoor {
  const path = pathname.replace(/\/+$/, '') || '/'
  const params = new URLSearchParams(search)
  if (path === SIGN_IN_PATH || hash.startsWith('#/') || params.has('__clerk_ticket') || params.has('__clerk_status')) {
    return 'sign-in'
  }
  const mayBeSignedIn = clerk.signedInHere === '1' || clerk.signedInHere === SIGNING_IN
  return !clerk.loaded && mayBeSignedIn ? 'wait' : 'landing'
}

/** `signedInHere` while the sign-in form shows (B51, #80). */
export const SIGNING_IN = 'pending'

/** The `signedInHere` value for Clerk's answer at this front door: `1` signed in, `0` signed out, and `pending` when
 * signed out on the sign-in form (B51, #80). After a sign-in Clerk loads `/` before it answers again; `pending` makes
 * that load wait instead of flashing the landing page. An abandoned sign-in only costs the next visit a short wait. */
export function rememberedSignIn(signedIn: boolean, door: FrontDoor): '1' | '0' | typeof SIGNING_IN {
  if (signedIn) return '1'
  return door === 'sign-in' ? SIGNING_IN : '0'
}
