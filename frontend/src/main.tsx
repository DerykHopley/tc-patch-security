import { lazy, StrictMode, Suspense, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { health, type AuthConfig } from './api.ts'
import App from './App.tsx'
import { SignInLoading, SignInScreen } from './auth/SignInScreen.tsx'
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
// fails outright shows the app, which says the backend is offline. Until it answers, the loading screen (#69): a
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
  if (!auth.on || !auth.publishable_key) return <App />
  return (
    <Suspense
      fallback={
        <SignInScreen>
          <SignInLoading />
        </SignInScreen>
      }
    >
      <ClerkApp publishableKey={auth.publishable_key} />
    </Suspense>
  )
}

const root = document.getElementById('root')
if (!root) throw new Error('index.html has no #root element')

createRoot(root).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
