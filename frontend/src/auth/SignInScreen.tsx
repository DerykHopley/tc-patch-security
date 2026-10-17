import { useState, useSyncExternalStore, type ReactNode } from 'react'
import { MoonIcon, ShieldIcon, SunIcon } from '../components/Icons.tsx'
import { Robot } from '../components/Robot.tsx'
import { pickPose } from '../components/patchPose.ts'
import { useTheme } from '../theme.ts'
import { NOT_INVITED, signInView, type SignInView } from './signInView.ts'

// The sign-in screen (B10, DESIGN.md §5.13): what a signed-out visitor sees with sign-in on. One Playful card on the
// page background, Patch rising over its top edge, the brand, a heading and one line, then Clerk's sign-in form
// (`children`), styled from our tokens. While Clerk loads, SignInLoading says so; if Clerk can't load, SignInFailed
// says what to do. B31: the view follows the address Clerk sends to (signInView.ts). An invitation link: "Join Patch"
// and Clerk's sign-up form. A sign-up without an invitation: Patch's own message in place of the form.

const SIGN_IN = {
  title: 'Sign in to Patch',
  lead: 'Patch is invite-only. Sign in with the email address your invitation went to.',
}
const TEXT: Record<SignInView, { title: string; lead: string }> = {
  'sign-in': SIGN_IN,
  invitation: { title: 'Join Patch', lead: "You're invited. Finish signing up below." },
  'not-invited': SIGN_IN,
}

function subscribe(onChange: () => void) {
  window.addEventListener('hashchange', onChange) // Clerk's hash routing moves by setting location.hash
  window.addEventListener('popstate', onChange)
  return () => {
    window.removeEventListener('hashchange', onChange)
    window.removeEventListener('popstate', onChange)
  }
}

/** The sign-in screen's view for the page's current address; follows Clerk's steps. */
export function useSignInView(): SignInView {
  return useSyncExternalStore(subscribe, () => signInView(window.location))
}

export function SignInScreen({ children }: { children: ReactNode }) {
  const view = useSignInView()
  const { title, lead } = TEXT[view]
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
        <div className="brand signin-brand">
          <span className="brand-mark">
            <ShieldIcon />
          </span>
          <span className="brand-name">
            <span>LLM Security</span>
            <small>assistant</small>
          </span>
        </div>
        <h1 id="signin-title">{title}</h1>
        <p className="signin-lead">{lead}</p>
        <div className="signin-form">{view === 'not-invited' ? <NotInvited /> : children}</div>
      </main>
    </div>
  )
}

/** A sign-up without an invitation (B31): said plainly on Patch's screen, never on Clerk's hosted page. */
function NotInvited() {
  return (
    <div className="signin-note signin-failed" role="alert">
      <p>{NOT_INVITED}</p>
      {/* `#/`: the first step of Clerk's sign-in form */}
      <button type="button" onClick={() => (window.location.hash = '/')}>
        Back to sign-in
      </button>
    </div>
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
