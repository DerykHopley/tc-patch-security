// Sign-in setup (B31, #78; open sign-up B38, #81): Clerk stays inside Patch, and the sign-in screen picks its view
// from the address.
//
// Clerk's checks are in docs/SOURCE-CHECKS.md (Clerk, B31 and B38). In short: without signInUrl and signUpUrl,
// Clerk's components send a sign-up (an SSO account it doesn't know) to the instance's hosted Account Portal. So every
// URL Clerk gets is a path on this page. `<SignIn withSignUp>` then runs its sign-up steps itself, under `#/create`.
// Sign-up is open (Clerk's Public mode, B38): anyone can make an account there, then asks the owner for access
// (access.ts). No invitations any more.

/** The URLs ClerkProvider gets: all on this page, so no step ever leaves Patch for Clerk's hosted page. */
export const CLERK_URLS = {
  signInUrl: '/',
  signUpUrl: '/#/create',
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
