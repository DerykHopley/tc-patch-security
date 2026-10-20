// Sign-in keeps where you were going (B60, #107). A signed-out visitor who opens an in-app address (an alert's
// `/cves/<id>`, Settings at the Requests card) gets the landing page, then the sign-in form; after sign-in Clerk
// would send them to `/`. So the front door keeps that address for this tab, Clerk's form is told to go there after
// sign-in or sign-up, and the app opens there once (route.ts `useRoute`), then forgets it.
//
// Per tab, in sessionStorage (DESIGN.md §11): Clerk's SSO round trip leaves the page and comes back to it, so memory
// isn't enough, and a target belongs to the tab whose link was opened. Every read and write is wrapped: blocked
// storage only means the app opens on the dashboard, as before.
//
// Only a same-origin path is ever kept or given out, never a full URL: a target that could point at another site
// would make the sign-in form an open redirect.

const KEY = 'signInTarget'
const MAX = 2048 // longer than any of Patch's own addresses

/** `value` as a path on this origin (`/cves/CVE-…?x#y`), or null. Refused: anything not text, not starting with a
 * single `/` (a full URL, `//host`, `/\host`, `javascript:`), holding a control character, space or backslash
 * (browsers drop tabs and newlines and read `\` as `/`, which can turn `/\t/host` into `//host`), too long, or
 * resolving to another origin. */
export function safeTarget(value: unknown, origin: string): string | null {
  if (typeof value !== 'string' || value.length > MAX) return null
  if (!value.startsWith('/') || value.startsWith('//')) return null
  // eslint-disable-next-line no-control-regex
  if (/[\u0000- \u007f\\]/.test(value)) return null
  let url: URL
  try {
    url = new URL(value, origin)
  } catch {
    return null
  }
  if (url.origin !== origin) return null
  const path = url.pathname + url.search + url.hash
  return path.startsWith('/') && !path.startsWith('//') ? path : null
}

/** The props that send Clerk's `<SignIn withSignUp>` to the target after a sign-in or a sign-up (a new account then
 * sees its access card there, and the app at that address once approved). The *force* props, because Clerk ranks them
 * above a `redirect_url` in the address and above `CLERK_URLS`' fallback (docs/SOURCE-CHECKS.md, Clerk B60). No
 * target: no props, so Clerk's fallback `/` stands. */
export function clerkRedirects(target: string | null): { forceRedirectUrl?: string; signUpForceRedirectUrl?: string } {
  return target ? { forceRedirectUrl: target, signUpForceRedirectUrl: target } : {}
}

export type TargetStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

/** This tab's sessionStorage, or null when the browser blocks it. */
function tabStorage(): TargetStorage | null {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

const here = () => window.location.origin

/** Keeps `target` for this tab when it's a safe path; null (or an unsafe one) forgets any older target. */
export function keepTarget(target: string | null, storage = tabStorage(), origin = here()): void {
  const path = safeTarget(target, origin)
  try {
    if (path) storage?.setItem(KEY, path)
    else storage?.removeItem(KEY)
  } catch {
    // blocked: nothing kept, the app opens on the dashboard after sign-in, as before
  }
}

/** The kept target, still kept (Clerk's form reads it on every render), or null. */
export function readTarget(storage = tabStorage(), origin = here()): string | null {
  try {
    return safeTarget(storage?.getItem(KEY), origin)
  } catch {
    return null
  }
}

/** The kept target, now forgotten: it's used once. */
export function takeTarget(storage = tabStorage(), origin = here()): string | null {
  const path = readTarget(storage, origin)
  try {
    storage?.removeItem(KEY)
  } catch {
    // blocked: there was nothing to forget
  }
  return path
}
