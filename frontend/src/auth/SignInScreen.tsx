import { useEffect, useState, useSyncExternalStore, type ReactNode } from 'react'
import { Brand } from '../components/Brand.tsx'
import { MoonIcon, SunIcon } from '../components/Icons.tsx'
import { Robot } from '../components/Robot.tsx'
import { pickPose } from '../components/patchPose.ts'
import { useTheme } from '../theme.ts'
import { signInView, type SignInView } from './signInView.ts'
import { rememberSigningIn, subscribeToAddress } from './useFrontDoor.ts'

// The sign-in screen (B10, DESIGN.md §5.13): what a signed-out visitor sees with sign-in on. One Playful card on the
// page background, Patch rising over its top edge, the brand, a heading and one line, then Clerk's sign-in form
// (`children`), styled from our tokens. While Clerk loads, SignInLoading says so; if Clerk can't load, SignInFailed
// says what to do. B38: sign-up is open, so Clerk's sign-up steps (`#/create`) are headed "Request access to Patch".
// `ScreenCard` is the same frame for the access screens (AccessScreen.tsx).

const TEXT: Record<SignInView, { title: string; lead: string }> = {
  'sign-in': {
    title: 'Sign in to Patch',
    lead: 'Sign in, or make an account and ask the owner for access.',
  },
  'sign-up': {
    title: 'Request access to Patch',
    lead: 'Make an account first. Then you ask the owner to let you in.',
  },
}

/** The sign-in screen's view for the page's current address; follows Clerk's steps. */
export function useSignInView(): SignInView {
  return useSyncExternalStore(subscribeToAddress, () => signInView(window.location))
}

export function SignInScreen({ children }: { children: ReactNode }) {
  const { title, lead } = TEXT[useSignInView()]
  useEffect(rememberSigningIn, []) // B51: the load of "/" after signing in waits for Clerk, no landing-page flash
  return <ScreenCard title={title} lead={lead}>{children}</ScreenCard>
}

/** The one-card screen (§5.13): the theme switch, Patch over the card's edge, the brand, a heading, a line, then
 * `children`. */
export function ScreenCard({ title, lead, children }: { title: string; lead: string; children: ReactNode }) {
  const [theme, toggleTheme] = useTheme()
  const [pose] = useState(() => pickPose('idle', Math.random)) // no mood here: idle, picked once (DESIGN.md §8.3)
  const dark = theme === 'dark'
  return (
    <div className="signin-page">
      <button
        type="button"
        className="theme-btn signin-theme"
        onClick={toggleTheme}
        aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
        title={dark ? 'Light mode' : 'Dark mode'}
      >
        {dark ? <SunIcon /> : <MoonIcon />}
      </button>
      <main className="signin-card" aria-labelledby="signin-title">
        <Robot size={110} variant={pose.variant} />
        <Brand className="signin-brand" />
        <h1 id="signin-title" tabIndex={-1}>{title}</h1>
        <p className="signin-lead">{lead}</p>
        <div className="signin-form">{children}</div>
      </main>
    </div>
  )
}

/** While Clerk loads, for a browser that was signed in last time (B42): no landing page flashing before the app. */
export function OpeningPatch() {
  return (
    <ScreenCard title="Opening Patch" lead="Checking that you're still signed in.">
      <output className="signin-note">Loading…</output>
    </ScreenCard>
  )
}

export function SignInLoading() {
  return (
    <output className="signin-note">
      Loading sign-in…
    </output>
  )
}

export function SignInFailed() {
  return (
    <div className="signin-note signin-failed" role="alert">
      <p>Sign-in didn't load. Check your connection, then reload the page.</p>
      <button type="button" onClick={() => window.location.reload()}>
        Reload
      </button>
    </div>
  )
}
