import { ClerkFailed, ClerkLoaded, ClerkLoading, ClerkProvider, SignIn, useAuth, useClerk, useUser } from '@clerk/react'
import { useEffect, useLayoutEffect, useState } from 'react'
import { setSessionToken } from '../api.ts'
import App from '../App.tsx'
import { SignInFailed, SignInLoading, SignInScreen } from './SignInScreen.tsx'

// Sign-in on (B10): Clerk's React package around the app. Loaded only when /health says sign-in is on (main.tsx),
// so with sign-in off nothing of Clerk's is fetched. Signed out: the sign-in screen. Signed in: the app, every API
// call with a fresh session token, and the user menu.

export default function ClerkApp({ publishableKey }: { publishableKey: string }) {
  return (
    <ClerkProvider publishableKey={publishableKey} afterSignOutUrl="/">
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
        {/* Invite-only: no sign-up link. Hash routing: the app's own paths stay the app's. */}
        <SignIn routing="hash" withSignUp={false} appearance={appearance} />
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
  const email = user?.primaryEmailAddress?.emailAddress ?? null
  const account = { name: user?.fullName?.trim() || email || user?.id || 'Signed in', email, onSignOut: () => signOut() }
  return <App account={account} />
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
