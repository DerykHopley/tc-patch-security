import { createContext, useContext, type ReactNode } from 'react'
import '../styles/settings.css'

// A card of the Settings and Dev pages (DESIGN.md §5.2): a title, then the card's content. Each card had a "Live" chip
// until B50 (#95): every card said it, so it told you nothing.

/** B48: the level of a card's title. Settings puts its cards under its two parts' headings ("Yours", "This Patch"),
 *  so there they are h3; elsewhere h2. */
export const CardLevel = createContext<2 | 3>(2)

// `anchor`: the section's id, for a link to the card (B38: an alert opens /settings#requests)
export function Card({ title, className = '', anchor, children }: {
  title: string
  className?: string
  anchor?: string
  children: ReactNode
}) {
  const id = `card-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`
  const Title = useContext(CardLevel) === 3 ? 'h3' : 'h2'
  return (
    <section id={anchor} className={`card settings-card ${className}`} aria-labelledby={id}>
      <div className="card-head">
        <Title id={id} className="card-title">{title}</Title>
      </div>
      {children}
    </section>
  )
}
