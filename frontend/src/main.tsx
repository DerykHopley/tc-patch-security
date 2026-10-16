import { lazy, StrictMode, Suspense, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { health, type AuthConfig } from './api.ts'
import App from './App.tsx'
import { SignInLoading, SignInScreen } from './auth/SignInScreen.tsx'
import './styles/tokens.css'
import './styles/shell.css'
import './styles/controls.css'
import './styles/robot.css'
import './styles/signin.css'

// Sign-in (B10): /health says whether it's on. Off (locally, the tests): the app as before. On: Clerk's code, a
// separate chunk loaded only then, decides between the sign-in screen and the app. A backend that doesn't answer
// shows the app, which says the backend is offline.
const ClerkApp = lazy(() => import('./auth/ClerkApp.tsx'))
const OFF: AuthConfig = { on: false, publishable_key: null }

function Root() {
  const [auth, setAuth] = useState<AuthConfig | null>(null)
  useEffect(() => {
    health().then(
      (h) => setAuth(h.auth ?? OFF),
      () => setAuth(OFF),
    )
  }, [])
  if (auth === null) return null // a moment: the app's first paint waits for /health
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
