import { useEffect, useState } from 'react'
import { WarningIcon } from '../components/Icons.tsx'

// An alert links to the app as `#cve=CVE-…` (DESIGN.md §6.4). Only a well-formed CVE id is accepted: the hash is
// text from outside, so nothing else from it reaches the page or the chat.
const ALERT_LINK = /^#cve=(CVE-\d{4}-\d{4,7})$/i

function cveFromHash(): string | null {
  return ALERT_LINK.exec(window.location.hash)?.[1]?.toUpperCase() ?? null
}

/** The CVE an alert link points at, until the banner is handled; also when a link is followed with the app open. */
export function useAlertLink(): [string | null, () => void] {
  const [cve, setCve] = useState(cveFromHash)

  useEffect(() => {
    const onHash = () => setCve(cveFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  // Handled: drop the hash, so a reload doesn't show the banner again.
  function done() {
    setCve(null)
    history.replaceState(null, '', window.location.pathname + window.location.search)
  }

  return [cve, done]
}

// The banner over the page: "Explain it" asks Patch about the CVE; Dismiss just closes it.
export function AlertBanner({ cve, onExplain, onDismiss }: {
  cve: string
  onExplain: () => void
  onDismiss: () => void
}) {
  return (
    <section className="alert-banner" aria-label="Alert">
      <WarningIcon />
      <p>
        You opened an alert for <strong>{cve}</strong>.
      </p>
      <button type="button" className="primary" onClick={onExplain}>
        Explain it
      </button>
      <button type="button" onClick={onDismiss}>
        Dismiss
      </button>
    </section>
  )
}
