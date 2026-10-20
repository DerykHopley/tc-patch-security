// The user menu's words (B10, DESIGN.md §5.13). Pure, so it's tested without React (userMenu.test.ts).

/** The one or two letters on the button: the first letters of the first two words of the name. */
export function initials(name: string): string {
  const words = name.trim().split(/[\s@._-]+/).filter(Boolean)
  return (words.length ? words.slice(0, 2).map((w) => w[0]).join('') : '?').toUpperCase()
}
