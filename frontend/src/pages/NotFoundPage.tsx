import { Robot, type Variant } from '../components/Robot.tsx'
import { followLink, PATHS } from '../route.ts'
import '../styles/landing.css' // the pill link (§5.16)
import '../styles/notFound.css'

// "Page not found" (B49, #96 O1; DESIGN.md §5.19): an address the app has no page for, signed in or with sign-in off.
// It used to show the dashboard under the bad address. In Patch's welcome look (§5.8): Patch idling over the card's
// top edge, what happened, and the way back. The address is shown as text, cut short: it is text from outside.

const SHOWN = 60 // characters of the address shown back

export function NotFoundPage({ path, variant, onNavigate }: {
  path: string
  variant: Variant
  onNavigate: (href: string) => void
}) {
  const shown = path.length > SHOWN ? `${path.slice(0, SHOWN)}…` : path
  return (
    <div className="page">
      <section className="not-found" aria-labelledby="not-found-title">
        <Robot size={110} pose={{ mood: 'idle', variant }} />
        <div className="not-found-body">
          <h2 id="not-found-title">Patch has no page here</h2>
          <p>
            Nothing lives at <code className="not-found-path">{shown}</code>. The link may be old, or mistyped.
          </p>
          <a className="pill-link primary" href={PATHS.dashboard} onClick={(e) => followLink(e, onNavigate)}>
            Open the dashboard
          </a>
        </div>
      </section>
    </div>
  )
}
