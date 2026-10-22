import { createContext, useContext, useState } from 'react'
import { Card } from '../components/StatusCard.tsx'
import { accountDetail, canUnlink, linkable, linkAccount, rows, type ClerkUserLike } from './linkedAccounts.ts'

// The Connected accounts card on Settings (B38, #81, DESIGN.md §5.7): every signed-in user lists the sign-in methods
// linked to their account, links another (Google, Discord) and unlinks one, never the last. With sign-in off there's
// no account, so no card. Clerk's user comes through this context from auth/ClerkApp.tsx, so Settings loads none of
// Clerk's code itself.
// F154 (#154): each account's email or username is hidden (not rendered) until Show details; every load starts
// hidden, so a screen share is safe. The provider's name stays, and Link and Unlink work either way.

export const LinkedAccountsContext = createContext<ClerkUserLike | null>(null)

export function ConnectedAccountsCard() {
  const user = useContext(LinkedAccountsContext)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [shown, setShown] = useState(false) // F154: never remembered
  if (!user) return null

  async function link(strategy: `oauth_${string}`) {
    if (!user) return
    setBusy(strategy)
    setError(null)
    setDone(null)
    try {
      await linkAccount(user, strategy, window.location.origin, (url) => window.location.assign(url))
    } catch (e) {
      setError((e as Error).message)
      setBusy(null)
    }
  }

  async function unlink(id: string, name: string) {
    const row = rows(user!).find((r) => r.account.id === id)
    if (!row) return
    setBusy(id)
    setError(null)
    setDone(null)
    try {
      await row.account.destroy()
      setDone(`${name} is no longer linked.`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const listed = rows(user)
  const offer = linkable(user)
  return (
    <Card title="Connected accounts" anchor="connected-accounts">
      <p className="meta">
        Sign in with any of these and you land in the same account. Linking works even when the other account uses
        another email.
      </p>
      {listed.length > 0 && (
        <button type="button" className="details-toggle" aria-pressed={shown} onClick={() => setShown((s) => !s)}>
          {shown ? 'Hide details' : 'Show details'}
        </button>
      )}
      <ul className="linked-list">
        {user.passwordEnabled && (
          <li className="linked-row">
            <span className="linked-name">Password</span>
            <span className="linked-detail">Email and password</span>
          </li>
        )}
        {listed.map((r) => {
          const last = !canUnlink(user, r.account)
          return (
            <li key={r.account.id} className="linked-row">
              <span className="linked-name">{r.name}</span>
              <span className="linked-detail">{accountDetail(r, shown)}</span>
              {r.error && <span className="linked-error">Not linked: {r.error}</span>}
              {last ? (
                <span className="linked-last">Your only way to sign in: link another first.</span>
              ) : (
                <button type="button" onClick={() => void unlink(r.account.id, r.name)} disabled={busy !== null}
                  aria-label={`Unlink ${r.name}`}>
                  {busy === r.account.id ? 'Unlinking…' : r.error ? 'Remove' : 'Unlink'}
                </button>
              )}
            </li>
          )
        })}
      </ul>
      {offer.length > 0 && (
        <div className="linked-add">
          {offer.map((p) => (
            <button key={p.strategy} type="button" onClick={() => void link(p.strategy)} disabled={busy !== null}>
              {busy === p.strategy ? `Opening ${p.name}…` : `Link ${p.name}`}
            </button>
          ))}
        </div>
      )}
      {error && <p role="alert" className="form-error">{error}</p>}
      {done && <output className="meta linked-done">{done}</output>}
    </Card>
  )
}
