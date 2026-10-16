import { useEffect, useId, useRef, useState } from 'react'
import { initials } from '../userMenu.ts'

// The user menu (B10, DESIGN.md §5.13): with sign-in on, a round button in the top bar with the user's initial; it
// opens a small card with their name and email and "Sign out". Esc or a click outside closes it, and the focus goes
// back to the button. Not shown with sign-in off.

export interface Account {
  name: string
  email: string | null
  onSignOut: () => Promise<void> | void
}

export function UserMenu({ account }: { account: Account }) {
  const [open, setOpen] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const button = useRef<HTMLButtonElement>(null)
  const box = useRef<HTMLDivElement>(null)
  const menuId = useId()

  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false)
        button.current?.focus()
      }
    }
    function onClick(e: MouseEvent) {
      if (!box.current?.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onClick)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onClick)
    }
  }, [open])

  async function signOut() {
    setLeaving(true)
    try {
      await account.onSignOut()
    } finally {
      setLeaving(false)
    }
  }

  return (
    <div className="user-menu" ref={box}>
      <button
        ref={button}
        type="button"
        className="user-btn"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={`Your account: ${account.name}`}
        title={account.name}
        onClick={() => setOpen(!open)}
      >
        <span aria-hidden="true">{initials(account.name)}</span>
      </button>
      {open && (
        <section className="user-card" id={menuId} aria-label="Your account">
          <strong className="user-name">{account.name}</strong>
          {account.email && account.email !== account.name && <span className="user-email">{account.email}</span>}
          <button type="button" className="user-signout" onClick={signOut} disabled={leaving} aria-busy={leaving}>
            {leaving ? 'Signing out…' : 'Sign out'}
          </button>
        </section>
      )}
    </div>
  )
}
