import { lazy, StrictMode, Suspense, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { health, type AuthConfig } from './api.ts'
import App from './App.tsx'
import { AccessGate } from './auth/AccessGate.tsx'
import { OpeningPatch, SignInLoading, SignInScreen } from './auth/SignInScreen.tsx'
import { useFrontDoor } from './auth/useFrontDoor.ts'
import { Landing } from './landing/Landing.tsx'
import { LoadingScreen } from './components/LoadingScreen.tsx'
import { waitForHealth, type HealthWait } from './healthWait.ts'
import './styles/tokens.css'
import './styles/shell.css'
import './styles/controls.css'
import './styles/robot.css'
import './styles/signin.css'
import './styles/loading.css'

// Sign-in (B10): /health says whether it's on. Off (locally, the tests): the app as before. On: Clerk's code, a
// separate chunk loaded only then, decides between the sign-in screen and the app. A /health that
// fails outright shows the app, which says the backend is offline. Signed out, the landing page (B42), which needs
// nothing but /health. Until it answers, the loading screen (#69): a
// /health that doesn't answer in 15 s (a cold start, a hung server) shows "Backend offline — retrying" there.
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
      onDone: (r) => setAuth(r.ok ? (r.health.auth ?? OFF) : OFF),
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
  return (
    <Suspense fallback={<SignedOutFallback />}>
      <ClerkApp publishableKey={auth.publishable_key} />
    </Suspense>
  )
}

/** Until Clerk's chunk loads: the same screen ClerkApp shows a signed-out visitor at this address (B42). */
function SignedOutFallback() {
  const door = useFrontDoor(false)
  if (door === 'landing') return <Landing place="front-door" />
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
