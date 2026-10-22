// Sign-up requests (B38, #81): who may use Patch with sign-in on. Sign-up is open in Clerk; a new account asks the
// owner, who approves it on Settings' Requests card. The words of the access screens and the card's buttons are here,
// pure, so `npm test` checks them without React (access.test.ts). The calls go through api.ts's request().
import { utcTime } from './freshness.ts'

export type AccessStatus = 'none' | 'waiting' | 'approved' | 'refused'

/** B45 (#90): what the owner lets someone do. "owner" is OWNER from the server's environment, never a stored role. */
export type StoredRole = 'viewer' | 'trusted' | 'reviewer'
export type UserRole = StoredRole | 'owner'

/** GET /access: the caller's own status (sign-in off: approved, the owner). */
export interface Access {
  status: AccessStatus
  owner: boolean
  role: UserRole // B45: read on each page load, so the owner's change shows on the next one
  sign_in: boolean
  note: string | null // the caller's own note, shown back to them only
  at: string | null
}

/** One person on the owner's Requests card. Name and email come from Clerk when the card opens; Patch keeps neither. */
export interface RequestRow {
  user_id: string
  status: Exclude<AccessStatus, 'none'>
  note: string | null
  by: string | null
  at: string | null
  requested_at: string | null
  migrated: boolean // approved before sign-up requests existed (they were invited)
  name: string | null
  email: string | null
  role: StoredRole // B45: viewer until the owner chooses another
}

export interface RequestsReply {
  requests: RequestRow[]
  names: boolean // false: no Clerk secret key on the server, or Clerk didn't answer: user ids only
  you: string // the owner's id: "by you"
}

export const NOTE_MAX = 280

/** Characters left for the note, counted as the server does: after trimming. Below 0: too long. */
export function noteLeft(note: string): number {
  return NOTE_MAX - note.trim().length
}

/** The screen a signed-in person who isn't approved sees, by their status. */
export function accessScreen(status: Exclude<AccessStatus, 'approved'>): { title: string; lead: string; form: boolean } {
  switch (status) {
    case 'none':
      return {
        title: 'Ask to join Patch',
        lead: 'Patch opens to the people its owner approves. Send a request and the owner gets a note; you can add a few words for them.',
        form: true,
      }
    case 'waiting':
      return {
        title: 'Your request is waiting for the owner',
        lead: "You'll get in once they approve it. Come back any time, or check again below.",
        form: false,
      }
    case 'refused':
      return {
        title: "Your request wasn't approved",
        lead: "The owner didn't approve this account for Patch. Thanks for asking.",
        form: false,
      }
  }
}

export type RequestAction = { label: string; to: 'approved' | 'refused' | 'waiting' | 'remove'; primary: boolean }

/** The Requests card's buttons for one person. */
export function requestActions(status: RequestRow['status']): RequestAction[] {
  switch (status) {
    case 'waiting':
      return [{ label: 'Approve', to: 'approved', primary: true }, { label: 'Refuse', to: 'refused', primary: false }]
    case 'approved':
      return [{ label: 'Remove', to: 'remove', primary: false }]
    case 'refused':
      return [{ label: 'Undo refusal', to: 'waiting', primary: false }, { label: 'Approve', to: 'approved', primary: true }]
  }
}

const DONE: Record<RequestRow['status'], string> = { waiting: '', approved: 'Approved', refused: 'Refused' }

/** The line under a person's name: when they asked, and who decided when. */
export function requestLine(r: RequestRow, me: string | null): string {
  if (r.migrated) return 'Approved before sign-up requests (they were invited)'
  const parts = r.requested_at ? [`Asked ${utcTime(r.requested_at)}`] : []
  if (r.status !== 'waiting' && r.by) {
    parts.push(`${DONE[r.status]} by ${r.by === me ? 'you' : r.by}${r.at ? ` ${utcTime(r.at)}` : ''}`)
  }
  return parts.join(' · ')
}

/** F154 (#154): who a person is on the Requests card. Shown: their name from Clerk (else the user id). Hidden, the
 * default, so a screen share is safe: their place in the list and the end of their user id, enough to tell rows apart
 * without naming anyone. The buttons' names and the status line use it too, so a screen reader can't leak a name. */
export function requestWho(r: RequestRow, index: number, shown: boolean): string {
  if (shown) return r.name ?? r.user_id
  return `Request ${index + 1} · id …${r.user_id.slice(-4)}`
}

// --- Roles (B45, #90): the owner's choice per approved person on the Requests card, and what each role sees

export const ROLE_CHOICES: { value: StoredRole; label: string; hint: string }[] = [
  { value: 'viewer', label: 'Viewer', hint: 'Dashboard, CVEs, chat and their own watchlist. No Dev page.' },
  { value: 'trusted', label: 'Trusted', hint: 'Also the Dev page, read-only, and the search playground.' },
  { value: 'reviewer', label: 'Reviewer', hint: 'Also tries other Dev settings: their changes apply only to them.' },
]

export function roleHint(role: StoredRole): string {
  return ROLE_CHOICES.find((c) => c.value === role)!.hint
}

/** The Requests card's status line after the owner changes someone's role. */
export function roleDone(who: string, role: StoredRole): string {
  const label = ROLE_CHOICES.find((c) => c.value === role)!.label
  return `${who} is now ${role === 'viewer' ? 'a Viewer' : label}: it applies on their next page load.`
}

/** The caller's role. null: /access hasn't answered, which only lets the app show with sign-in off (AccessGate),
 * where the one local user is the owner. */
export function roleOf(access: Access | null): UserRole {
  return access?.role ?? 'owner'
}

/** Viewers see no Dev page (its internals aren't for them); the server refuses them its routes too. */
export function seesDev(role: UserRole): boolean {
  return role !== 'viewer'
}

/** B49 (#96 C1): the usage line under each answer (tokens, calls, cost) is for the people who change models, the owner
 * and Reviewers (their own Dev copy, B45). For everyone else it was noise about a bill they don't pay. */
export function seesUsage(role: UserRole): boolean {
  return role === 'owner' || role === 'reviewer'
}

const OWNERS_CHOICES ="These are the owner's choices: the chat and search use them for everyone. Only the owner can change them."
const REVIEWERS = "Your settings apply only to you: your chat and the playground use them, everyone else keeps the owner's."

/** The Dev page by role: whether the form shows (the owner's are everyone's, a reviewer's their own copy), whether
 * the model and retrieval checks can run (the owner's key), and the note line under the intro (null: the owner's). */
export function devView(role: UserRole, ownCopy: boolean): { change: boolean; runChecks: boolean; note: string | null } {
  if (role === 'owner') return { change: true, runChecks: true, note: null }
  if (role === 'reviewer') {
    return { change: true, runChecks: false, note: `${REVIEWERS} ${ownCopy ? "You've changed them." : "They start as the owner's."}` }
  }
  return { change: false, runChecks: false, note: OWNERS_CHOICES }
}
