import {
  ClerkFailed,
  ClerkLoaded,
  ClerkLoading,
  ClerkProvider,
  SignIn,
  useAuth,
  useClerk,
  useReverification,
  useUser,
} from '@clerk/react'
import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { setSessionToken } from '../api.ts'
import App from '../App.tsx'
import { AccessGate } from './AccessGate.tsx'
import { LinkedAccountsContext } from './ConnectedAccounts.tsx'
import type { ClerkAccount, ClerkUserLike } from './linkedAccounts.ts'
import { SignInFailed, SignInLoading, SignInScreen } from './SignInScreen.tsx'
import { CLERK_URLS } from './signInView.ts'

// Sign-in on (B10): Clerk's React package around the app. Loaded only when /health says sign-in is on (main.tsx),
// so with sign-in off nothing of Clerk's is fetched. Signed out: the sign-in screen. Signed in: the access gate
// (B38: the app only once the owner approved this account), every API call with a fresh session token, the user
// menu, and Clerk's user for the Connected accounts card.
// B31 (#78): every URL Clerk gets is on this page, so no step (an SSO sign-up included) falls back to Clerk's hosted
// Account Portal. B38 (#81): sign-up is open (Clerk's Public mode); its steps run inside <SignIn withSignUp>.

export default function ClerkApp({ publishableKey }: { publishableKey: string }) {
  return (
    <ClerkProvider publishableKey={publishableKey} {...CLERK_URLS}>
      <Gate />
    </ClerkProvider>
  )
}

function Gate() {
  const { isSignedIn } = useAuth()
  const appearance = useTokenAppearance()
  if (isSignedIn) return <SignedInApp />
  return (
    <SignInScreen>
      <ClerkLoading>
        <SignInLoading />
      </ClerkLoading>
      <ClerkFailed>
        <SignInFailed />
      </ClerkFailed>
      <ClerkLoaded>
        {/* Hash routing: the app's own paths stay the app's. Sign-in, with the sign-up steps (open sign-up, B38, and
            those an SSO sign-in can need) kept inside it under #/create. */}
        <SignIn routing="hash" withSignUp appearance={appearance} />
      </ClerkLoaded>
    </SignInScreen>
  )
}

function SignedInApp() {
  const { getToken } = useAuth()
  const { user } = useUser()
  const { signOut } = useClerk()
  // A layout effect runs before the app's own effects make their first API calls
  useLayoutEffect(() => {
    setSessionToken(() => getToken())
    return () => setSessionToken(null)
  }, [getToken])
  useLayoutEffect(dropClerkParams, [])
  // Clerk asks the user to confirm who they are again before a sensitive change, when the instance requires it
  // (its "reverification", in a dialog on this page): linking and unlinking go through it, as in Clerk's own profile.
  const createExternalAccount = useReverification(
    (params: Parameters<ClerkUserLike['createExternalAccount']>[0]) =>
      user!.createExternalAccount(params as Parameters<NonNullable<typeof user>['createExternalAccount']>[0]),
  )
  const destroy = useReverification((account: { destroy: () => Promise<void> }) => account.destroy())
  const linked = useMemo<ClerkUserLike | null>(() => user ? {
    passwordEnabled: user.passwordEnabled,
    externalAccounts: user.externalAccounts.map((a): ClerkAccount => ({
      id: a.id, provider: a.provider, emailAddress: a.emailAddress, username: a.username,
      verification: a.verification ? { status: a.verification.status, error: a.verification.error } : null,
      destroy: () => destroy(a).then(() => undefined),
    })),
    createExternalAccount: (params) => createExternalAccount(params),
  } : null, [user, createExternalAccount, destroy])
  const email = user?.primaryEmailAddress?.emailAddress ?? null
  const account = { name: user?.fullName?.trim() || email || user?.id || 'Signed in', email, onSignOut: () => signOut() }
  return (
    <LinkedAccountsContext.Provider value={linked}>
      <AccessGate signIn onSignOut={() => signOut()}>
        <App account={account} />
      </AccessGate>
    </LinkedAccountsContext.Provider>
  )
}

/** Back from Clerk (an old invitation link, an SSO or linking round trip): its query parameters leave the address bar
 * (and so bookmarks and history). */
function dropClerkParams() {
  const url = new URL(window.location.href)
  if (!url.searchParams.has('__clerk_ticket') && !url.searchParams.has('__clerk_status')) return
  url.searchParams.delete('__clerk_ticket')
  url.searchParams.delete('__clerk_status')
  window.history.replaceState(window.history.state, '', url)
}

/** Clerk's form in our tokens (DESIGN.md §3), read from the page so light and dark both follow the theme switch. */
function useTokenAppearance() {
  // re-render on a theme switch, so the tokens below are read again
  const [, setTheme] = useState(() => document.documentElement.dataset.theme)
  useEffect(() => {
    const watch = new MutationObserver(() => setTheme(document.documentElement.dataset.theme))
    watch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => watch.disconnect()
  }, [])
  const css = getComputedStyle(document.documentElement)
  const token = (name: string) => css.getPropertyValue(name).trim()
  return {
    variables: {
      colorPrimary: token('--accent'),
      colorPrimaryForeground: token('--on-primary'),
      colorBackground: token('--surface'),
      colorForeground: token('--text'),
      colorMutedForeground: token('--muted'),
      colorInput: token('--surface'),
      colorInputForeground: token('--text'),
      colorBorder: token('--border'),
      colorDanger: token('--error'),
      fontFamily: token('--font-body'),
      borderRadius: token('--radius-input'),
    },
    elements: {
      // Our card is the frame: Clerk's own card loses its shadow, border and heading
      rootBox: { width: '100%' },
      cardBox: { width: '100%', boxShadow: 'none', border: 'none' },
      card: { boxShadow: 'none', border: 'none', padding: '0.5rem 0' },
      header: { display: 'none' },
    },
  }
}
