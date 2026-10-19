// Sign-up requests (B38, #81): who may use Patch with sign-in on. Sign-up is open in Clerk; a new account asks the
// owner, who approves it on Settings' Requests card. The words of the access screens and the card's buttons are here,
// pure, so `npm test` checks them without React (access.test.ts). The calls go through api.ts's request().
import { utcTime } from './freshness.ts'

export type AccessStatus = 'none' | 'waiting' | 'approved' | 'refused'

/** GET /access: the caller's own status (sign-in off: approved, the owner). */
export interface Access {
  status: AccessStatus
  owner: boolean
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
