import { useContext, useEffect, useId, useRef, useState } from 'react'
import { menuLabel } from '../profile.ts'
import { initials } from '../userMenu.ts'
import { PersonIcon } from './Icons.tsx'
import { ProfileContext } from './Profile.tsx'

// The user menu (B10, DESIGN.md §5.13): with sign-in on, a round button in the top bar; it opens a small card with
// "Sign out". Esc or a click outside closes it, and the focus goes back to the button. Not shown with sign-in off.
// B48 (#77): anonymous by default: a person icon and "Your account". With a display name from the user's profile,
// their initials and the name. Never Clerk's name or email.

export interface Account {
  onSignOut: () => Promise<void> | void
}

export function UserMenu({ account }: { account: Account }) {
  const [open, setOpen] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const button = useRef<HTMLButtonElement>(null)
  const box = useRef<HTMLDivElement>(null)
  const menuId = useId()
  const { name } = useContext(ProfileContext)

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
        aria-label={menuLabel(name)}
        title={menuLabel(name)}
        onClick={() => setOpen(!open)}
      >
        {name ? <span aria-hidden="true">{initials(name)}</span> : <PersonIcon />}
      </button>
      {open && (
        <section className="user-card" id={menuId} aria-label="Your account">
          <strong className="user-name">{name ?? 'Your account'}</strong>
          {!name && <span className="user-email">No display name. You can add one on Settings, under Profile.</span>}
          <button type="button" className="user-signout" onClick={signOut} disabled={leaving} aria-busy={leaving}>
            {leaving ? 'Signing out…' : 'Sign out'}
          </button>
        </section>
      )}
    </div>
  )
}
