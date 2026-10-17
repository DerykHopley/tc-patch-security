// Sign-in setup (B31, #78): Clerk stays inside Patch, and the sign-in screen picks its view from the address.
//
// Clerk's checks are in docs/SOURCE-CHECKS.md (Clerk, B31). In short: without signInUrl and signUpUrl, Clerk's
// components send a sign-up (an SSO account it doesn't know) to the instance's hosted Account Portal. So every URL
// Clerk gets is a path on this page. `<SignIn withSignUp>` then runs its sign-up steps itself, under `#/create`.
// Patch is invite-only (Clerk's Restricted mode): there, `#/create` without an invitation is only ever Clerk's "access
// restricted" card, so Patch shows its own message instead. An invitation link (sent with Patch's address as its
// redirect) arrives with `?__clerk_ticket=…`: that's Clerk's `<SignUp>`, which reads the ticket and offers a password
// or the SSO providers.

/** The URLs ClerkProvider gets: all on this page, so no step ever leaves Patch for Clerk's hosted page. */
export const CLERK_URLS = {
  signInUrl: '/',
  signUpUrl: '/#/create',
  signInFallbackRedirectUrl: '/',
  signUpFallbackRedirectUrl: '/',
  afterSignOutUrl: '/',
} as const

export const NOT_INVITED = "This account isn't invited to Patch. Ask the owner for an invitation."

export type SignInView = 'sign-in' | 'invitation' | 'not-invited'

/** Which view the sign-in screen shows at this address (`window.location`'s search and hash). */
export function signInView({ search, hash }: { search: string; hash: string }): SignInView {
  const query = new URLSearchParams(search)
  const status = query.get('__clerk_status')
  if (query.get('__clerk_ticket') && status !== 'sign_in' && status !== 'complete') return 'invitation'
  const [path, hashQuery = ''] = hash.replace(/^#/, '').split('?', 2)
  if (path.replace(/\/$/, '') === '/create' && !new URLSearchParams(hashQuery).get('__clerk_ticket')) {
    return 'not-invited'
  }
  return 'sign-in'
}
