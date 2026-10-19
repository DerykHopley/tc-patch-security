import type { ReactNode } from 'react'
import '../styles/settings.css'

// A card of the Settings and Dev pages (DESIGN.md §5.2): a title and a chip saying what the card really does today.

export type Kind = 'live' | 'saved' | 'mock'
const KIND_LABEL: Record<Kind, string> = { live: 'Live', saved: 'Saved for later', mock: 'Mock' }

function Status({ kind, why }: { kind: Kind; why: string }) {
  return (
    <span className={`status-chip ${kind}`} title={why}>
      {KIND_LABEL[kind]}
    </span>
  )
}

// `anchor`: the section's id, for a link to the card (B38: an alert opens /settings#requests)
export function Card({ title, kind, why, className = '', anchor, children }: {
  title: string
  kind: Kind
  why: string
  className?: string
  anchor?: string
  children: ReactNode
}) {
  const id = `card-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`
  return (
    <section id={anchor} className={`card settings-card ${className}`} aria-labelledby={id}>
      <div className="card-head">
        <h2 id={id}>{title}</h2>
        <Status kind={kind} why={why} />
      </div>
      {children}
    </section>
  )
}
