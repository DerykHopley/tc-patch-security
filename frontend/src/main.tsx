import { lazy, StrictMode, Suspense, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { health, type AuthConfig } from './api.ts'
import App from './App.tsx'
import { AccessGate } from './auth/AccessGate.tsx'
import { OpeningPatch, SignInLoading, SignInScreen } from './auth/SignInScreen.tsx'
import { keepTarget } from './auth/signInTarget.ts'
import type { FrontDoor } from './auth/signInView.ts'
import { useFrontDoor } from './auth/useFrontDoor.ts'
import { Landing } from './landing/Landing.tsx'
import { LoadingScreen } from './components/LoadingScreen.tsx'
import { waitForHealth, type HealthWait } from './healthWait.ts'
import { signInTargetAt } from './route.ts'
import './styles/tokens.css'
import './styles/shell.css'
import './styles/controls.css'
import './styles/robot.css'
import './styles/signin.css'
import './styles/loading.css'

// Sign-in (B10): /health says whether it's on. Off (locally, the tests): the app as before. On: Clerk's code, a
// separate chunk loaded only then, decides between the sign-in screen and the app. A /health that
// fails outright retries on the loading screen like one that hangs (B46): without it nobody knows whether sign-in is
// on, so the app (its shell) never shows on a guess. Signed out, the landing page (B42), which needs
// nothing but /health. Until it answers, the loading screen (#69): a
// /health that doesn't answer in 15 s (a cold start, a hung server) shows "Patch's server isn't answering yet." there.
const ClerkApp = lazy(() => import('./auth/ClerkApp.tsx'))
const OFF: AuthConfig = { on: false, publishable_key: null }

function Root() {
  const [auth, setAuth] = useState<AuthConfig | null>(null)
  const [wait, setWait] = useState<HealthWait | null>(null)
  const retry = useRef<() => void>(() => {})
  useEffect(() => {
    const w = waitForHealth({
      fetchHealth: health,
      onChange: setWait,
      onDone: (r) => setAuth(r.health.auth ?? OFF),
    })
    retry.current = w.retryNow
    return w.stop // StrictMode's second run, or unmount: the first wait asks and reports nothing more
  }, [])
  if (auth === null) return <LoadingScreen wait={wait} onRetry={() => retry.current()} />
  if (!auth.on || !auth.publishable_key) {
    return (
      <AccessGate signIn={false}>
        <App />
      </AccessGate>
    )
  }
  return <SignInOn publishableKey={auth.publishable_key} />
}

/** Sign-in on. The landing page is drawn here, outside the Suspense boundary and outside ClerkProvider, so it stays
 * one element while Clerk's chunk loads (#100): drawn once by the fallback and once by ClerkApp, React swapped one for
 * the other ~300 ms in, and the page faded up twice. Until ClerkApp has said, the same rule as its fallback decides
 * (useFrontDoor, Clerk not loaded); then ClerkApp's own answer (`onLanding`), which knows sign-in and Clerk failing. */
function SignInOn({ publishableKey }: { publishableKey: string }) {
  const door = useFrontDoor(false)
  const [reported, setReported] = useState<boolean | null>(null)
  const landing = reported ?? door === 'landing'
  // B60 (#107): the address this signed-out visitor asked for, kept for this tab, so sign-in opens it (route.ts);
  // at "/" an older one is forgotten. Its own Sign in and Request access need nothing more. A layout effect, so it's
  // kept before the landing page is painted: with useEffect, a page left the moment it showed could lose it (the
  // B60.7 race, 2026-10-20).
  useLayoutEffect(() => {
    if (landing) keepTarget(signInTargetAt(window.location))
  }, [landing])
  return (
    <>
      {landing && <Landing place="front-door" />}
      <Suspense fallback={landing ? null : <SignedOutFallback door={door} />}>
        <ClerkApp publishableKey={publishableKey} onLanding={setReported} />
      </Suspense>
    </>
  )
}

/** Until Clerk's chunk loads, when it isn't the landing page: the screen ClerkApp shows at this address (B42). */
function SignedOutFallback({ door }: { door: FrontDoor }) {
  if (door === 'wait') return <OpeningPatch />
  return (
    <SignInScreen>
      <SignInLoading />
    </SignInScreen>
  )
}

const root = document.getElementById('root')
if (!root) throw new Error('index.html has no #root element')

createRoot(root).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
