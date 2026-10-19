// Your profile (B48, #97; the decisions of #77): anonymous by default, an optional display name the user gives
// Patch. Its words and the name's rules, the same as the server's (backend/app/profile.py). Pure: `npm test` checks
// them (profile.test.ts).

export const NAME_MAX = 60

/** One line of plain text: control characters dropped, runs of spaces made one, trimmed; null when empty. */
export function cleanName(name: string): string | null {
  // eslint-disable-next-line no-control-regex
  const text = name.replace(/[\u0000-\u001f\u007f]/g, ' ').split(/\s+/).filter(Boolean).join(' ')
  return text || null
}

/** Why the name can't be saved, or null. */
export function nameProblem(name: string): string | null {
  const n = cleanName(name)?.length ?? 0
  return n > NAME_MAX ? `A display name can be at most ${NAME_MAX} characters: this one has ${n}.` : null
}

/** The user menu button's name: "Your account", with the display name when one is given. */
export function menuLabel(name: string | null): string {
  return name ? `Your account: ${name}` : 'Your account'
}

// The other users' Alerts card (B48): their alerts stay in Patch; the channels are the owner's
export const IN_PATCH_NOTE =
  'Your alerts show here in Patch (Recent alerts, the New badge). Phone and email alerts go to the owner.'
