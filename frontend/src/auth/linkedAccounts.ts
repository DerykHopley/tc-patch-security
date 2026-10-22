// Connected accounts (B38, #81): link another sign-in method (Google, Discord) to the account you're signed in with,
// so it keeps the same Clerk user id even when that provider's email differs. Clerk links an SSO login to an
// existing account by itself only when the verified emails match (docs/SOURCE-CHECKS.md, Clerk B38).
//
// How (checked in Clerk's docs and in @clerk/ui 1.38.1's own UserProfile code, docs/SOURCE-CHECKS.md):
// `user.createExternalAccount({ strategy, redirectUrl })` returns an external account whose
// `verification.externalVerificationRedirectURL` is the provider's page; the page goes there, and the provider sends
// the browser back to `redirectUrl` on Patch. Clerk's own pages are never used. Unlink: `account.destroy()`.
// Pure over a small slice of Clerk's user, so `npm test` checks it on a fake (linkedAccounts.test.ts).

export interface ClerkAccount {
  id: string
  provider: string // "google", "discord"
  emailAddress: string
  username?: string | null
  verification: { status: string | null; error: { longMessage?: string; message?: string } | null } | null
  destroy: () => Promise<void>
}

export interface ClerkUserLike {
  passwordEnabled: boolean
  externalAccounts: ClerkAccount[]
  createExternalAccount: (params: { strategy: `oauth_${string}`; redirectUrl: string }) => Promise<{
    verification: { externalVerificationRedirectURL: URL | null } | null
  }>
}

/** The providers Patch offers to link: the ones the README asks the owner to switch on in Clerk (the free plan
 * allows three). One not switched on fails with Clerk's own message. */
export const PROVIDERS = [
  { strategy: 'oauth_discord', provider: 'discord', name: 'Discord' },
  { strategy: 'oauth_google', provider: 'google', name: 'Google' },
] as const

const NAMES: Record<string, string> = Object.fromEntries(PROVIDERS.map((p) => [p.provider, p.name]))
const providerName = (p: string) => NAMES[p] ?? p.charAt(0).toUpperCase() + p.slice(1)

const verified = (a: ClerkAccount) => a.verification?.status === 'verified'
const failed = (a: ClerkAccount) => !verified(a) && !!a.verification?.error

/** What the card lists: every linked account, and a link that failed, with Clerk's reason. One still on its way
 * (no error yet) isn't listed, as in Clerk's own profile page. */
export function rows(user: ClerkUserLike): { account: ClerkAccount; name: string; detail: string; error: string | null }[] {
  return user.externalAccounts.filter((a) => verified(a) || failed(a)).map((a) => ({
    account: a,
    name: providerName(a.provider),
    detail: a.username || a.emailAddress,
    error: verified(a) ? null : a.verification?.error?.longMessage || a.verification?.error?.message || 'Not linked.',
  }))
}

/** F154 (#154): an account's email or username, or, hidden (the default), only that it is hidden. */
export function accountDetail(row: { detail: string }, shown: boolean): string {
  return shown ? row.detail : 'Details hidden'
}

/** The providers not linked yet. */
export function linkable(user: ClerkUserLike) {
  const linked = new Set(user.externalAccounts.filter(verified).map((a) => a.provider))
  return PROVIDERS.filter((p) => !linked.has(p.provider))
}

/** Where the provider sends the browser back: Settings, at this card. */
export function linkRedirectUrl(origin: string): string {
  return `${origin}/settings#connected-accounts`
}

/** Start linking: ask Clerk for the provider's page, then go there. */
export async function linkAccount(user: ClerkUserLike, strategy: `oauth_${string}`, origin: string,
  go: (url: string) => void): Promise<void> {
  const created = await user.createExternalAccount({ strategy, redirectUrl: linkRedirectUrl(origin) })
  const url = created.verification?.externalVerificationRedirectURL
  if (!url) throw new Error("Clerk didn't give an address to link with. Try again.")
  go(url.href)
}

/** Never the last way to sign in: a password, or another linked account, must stay. A failed link isn't a way in,
 * so it can always go. Conservative: an email code sign-in, if the instance allows it, isn't counted. */
export function canUnlink(user: ClerkUserLike, account: ClerkAccount): boolean {
  if (!verified(account)) return true
  const others = user.externalAccounts.filter((a) => a.id !== account.id && verified(a)).length
  return user.passwordEnabled || others > 0
}
