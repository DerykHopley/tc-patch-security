import { useState } from 'react'
import { store } from '../storage.ts'
import { Robot, type Variant } from './Robot.tsx'

// Patch says hello above the dashboard (DESIGN.md §5.8), until it's closed: remembered in this browser (§11).
// "Ask Patch" opens the chat. Patch is idle here, in the variant picked on page load (§8.3).
const TITLE = "Hi there! I'm Patch, your security sidekick."

export function WelcomeBanner({ onAsk, variant }: { onAsk: () => void; variant: Variant }) {
  const [hidden, setHidden] = useState(() => store.get('helloHidden') === '1')
  if (hidden) return null

  function close() {
    store.set('helloHidden', '1')
    setHidden(true)
  }

  return (
    <section className="hello" aria-labelledby="hello-title">
      <button type="button" className="hello-close" onClick={close} aria-label="Close Patch's welcome" title="Close">
        <span aria-hidden="true">✕</span>
      </button>
      <Robot size={110} variant={variant} />
      <div className="hello-body">
        <h2 id="hello-title">{TITLE}</h2>
        <p>I watch the CVEs in your LLM stack and can explain any of them, or how to defend against them. Just ask.</p>
        <button type="submit" onClick={onAsk}>
          Ask Patch
        </button>
      </div>
    </section>
  )
}
