// Settings' "Start over" card (B50, #95; "Reset demo data" until then): exactly what the reset deletes and what it
// keeps, by role. The backend's State.reset deletes the caller's whole state but the profile and (the owner's) server
// settings, so the list follows its parts (backend/app/state.py). Plain functions, so `npm test` checks the words.
import type { UserRole } from './access.ts'

export const START_OVER_BUTTON = 'Reset all my data'

/** What a reset deletes, one item per line. The owner's state also holds the Dev page's choices (everyone's chat
 *  uses them), the channels and the schedule; a Reviewer's, their own copy of the Dev settings (B45). */
export function resetDeletes(role: UserRole): string[] {
  const out = [
    'Your watchlist and how you run each product (back to the default watchlist)',
    'Every CVE status you set, with its whole decision history',
    'Your alert rules, your priority and due-date policy and how Patch pitches its answers',
    'Your alerts log, the New marks and any change Patch proposed that you haven\'t approved',
  ]
  if (role === 'owner') {
    out.push('Your alert channels, the refresh schedule and any alert held for quiet hours or waiting for a retry',
      'The Dev page\'s choices: everyone\'s chat goes back to the default model and search settings')
  }
  if (role === 'reviewer') out.push('Your own copy of the Dev settings')
  return out
}

/** What a reset keeps. */
export function resetKeeps(role: UserRole): string {
  return role === 'owner'
    ? 'Kept: your display name and the server settings (the data source, the NVD key, how each channel is set up).'
    : 'Kept: your display name.'
}
