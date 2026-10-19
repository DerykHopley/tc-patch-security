// Counts in words (B49 C2, #96): one helper wherever a number and its noun are shown, so "1 sources · 1 tool calls"
// can't happen again. English only: one is singular, every other number (0 too) plural.

/** "1 source", "2 sources", "12,345 tokens". `plural`: for a word that doesn't just add an s ("entries"). */
export function count(n: number, word: string, plural = `${word}s`): string {
  return `${n.toLocaleString('en')} ${n === 1 ? word : plural}`
}
