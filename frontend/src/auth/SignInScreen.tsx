import { useState, type ReactNode } from 'react'
import { MoonIcon, ShieldIcon, SunIcon } from '../components/Icons.tsx'
import { Robot } from '../components/Robot.tsx'
import { pickPose } from '../components/patchPose.ts'
import { useTheme } from '../theme.ts'

// The sign-in screen (B10, DESIGN.md §5.13): what a signed-out visitor sees with sign-in on. One Playful card on the
// page background, Patch rising over its top edge, the brand, a heading and one line, then Clerk's sign-in form
// (`children`), styled from our tokens. While Clerk loads, SignInLoading says so; if Clerk can't load, SignInFailed
// says what to do.

export function SignInScreen({ children }: { children: ReactNode }) {
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
        <h1 id="signin-title">Sign in to Patch</h1>
        <p className="signin-lead">
          Patch is invite-only. Sign in with the email address your invitation went to.
        </p>
        <div className="signin-form">{children}</div>
      </main>
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
