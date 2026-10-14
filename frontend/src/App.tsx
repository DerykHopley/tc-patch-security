import { useEffect, useState } from 'react'
import { health, type Health } from './api.ts'

// The walking skeleton's bare page: proves the frontend reaches the backend.
// A02 replaces it with the design tokens and the app shell (docs/design/DESIGN.md).
export default function App() {
  const [info, setInfo] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    health().then(setInfo, (e: Error) => setError(e.message))
  }, [])

  return (
    <main>
      <h1>Patch</h1>
      {info && (
        <p>
          Data as of {info.as_of} · {info.model}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {!info && !error && <p>Loading…</p>}
    </main>
  )
}
