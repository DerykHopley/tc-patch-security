import type { Decision } from './api.ts'

/** Who decided and where, in a CVE's history (B44 D4, #94): "by you, on the CVEs page". Every record in a history is
 *  the viewer's own: each user's statuses and decisions live in their own state, and only they write it (B09; the
 *  owner's adopted pre-sign-in state is theirs too, B31). So the saved name ("owner" with sign-in off, the user's name
 *  with it on) reads "you". A status saved before decision records names nobody: "unknown". */
export function whoDecided(h: Pick<Decision, 'decided_by' | 'via'>): string {
  const who = h.decided_by === null ? 'by unknown' : 'by you'
  const where = h.via === 'chat' ? ', in the chat' : h.via === 'page' ? ', on the CVEs page' : ''
  return who + where
}
