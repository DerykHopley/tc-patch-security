import {
  ClerkFailed,
  ClerkLoaded,
  ClerkLoading,
  ClerkProvider,
  SignIn,
  SignUp,
  useAuth,
  useClerk,
  useUser,
} from '@clerk/react'
import { useEffect, useLayoutEffect, useState } from 'react'
import { setSessionToken } from '../api.ts'
import App from '../App.tsx'
import { SignInFailed, SignInLoading, SignInScreen, useSignInView } from './SignInScreen.tsx'
import { CLERK_URLS, NOT_INVITED } from './signInView.ts'

// Sign-in on (B10): Clerk's React package around the app. Loaded only when /health says sign-in is on (main.tsx),
// so with sign-in off nothing of Clerk's is fetched. Signed out: the sign-in screen. Signed in: the app, every API
// call with a fresh session token, and the user menu.
// B31 (#78): every URL Clerk gets is on this page, so no step (an SSO sign-up included) falls back to Clerk's hosted
// Account Portal. Email and password or an SSO provider, invite-only: docs/SOURCE-CHECKS.md (Clerk, B31).

// Clerk's own words where it refuses a sign-up, in case one shows inside its form: the same sentence as Patch's
// screen. Clerk looks up `unstable__errors.<error code>` for any code (checked in @clerk/ui's code);
// `sign_up_mode_restricted` isn't in its types, hence the plain record.
const REFUSED: Record<string, string> = { sign_up_mode_restricted: NOT_INVITED, not_allowed_access: NOT_INVITED }
const LOCALIZATION = {
  signUp: { restrictedAccess: { title: 'Not invited', subtitle: NOT_INVITED } },
  unstable__errors: { ...REFUSED },
}

export default function ClerkApp({ publishableKey }: { publishableKey: string }) {
  return (
    <ClerkProvider publishableKey={publishableKey} {...CLERK_URLS} localization={LOCALIZATION}>
      <Gate />
    </ClerkProvider>
  )
}

function Gate() {
  const { isSignedIn } = useAuth()
  const view = useSignInView()
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
        {/* Hash routing: the app's own paths stay the app's. An invitation link: Clerk's sign-up form reads its
            ticket. Otherwise sign-in, with the sign-up steps an SSO sign-in can need (withSignUp) kept inside it. */}
        {view === 'invitation' ? (
          <SignUp routing="hash" signInUrl={CLERK_URLS.signInUrl} appearance={appearance} />
        ) : (
          <SignIn routing="hash" withSignUp appearance={appearance} />
        )}
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
  useLayoutEffect(dropInvitationTicket, [])
  const email = user?.primaryEmailAddress?.emailAddress ?? null
  const account = { name: user?.fullName?.trim() || email || user?.id || 'Signed in', email, onSignOut: () => signOut() }
  return <App account={account} />
}

/** Signed in from an invitation link: the used ticket leaves the address bar (and so bookmarks and history). */
function dropInvitationTicket() {
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
