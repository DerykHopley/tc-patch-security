import type { OpenRouterModel } from '../api.ts'

// The OpenRouter model dropdown's words and its pick (A11.10): prices and the model-check score at the point of
// choice. Pure, so `npm test` checks them.

/** The select's last option: a model id typed by hand. Not a valid id (no slash), so it can't clash with one. */
export const OTHER = 'other'

function dollars(perMillion: number | null): string {
  if (perMillion === null) return '?'
  if (perMillion > 0 && perMillion < 0.1) return `$${Number(perMillion.toPrecision(2))}`
  return `$${perMillion.toFixed(2)}`
}

/** "$0.10 / $0.50 per M tokens": input, then output. A variable price (OpenRouter's -1) is unknown, never $0. */
export function priceText(m: OpenRouterModel): string {
  if (m.input_per_m === null && m.output_per_m === null) return 'price unknown'
  if (m.input_per_m === 0 && m.output_per_m === 0) return 'free'
  return `${dollars(m.input_per_m)} / ${dollars(m.output_per_m)} per M tokens`
}

export function optionText(m: OpenRouterModel, defaultId: string): string {
  const parts = [m.id === defaultId ? `${m.id} (default)` : m.id, priceText(m)]
  if (m.check) parts.push(`${m.check.passed}/${m.check.total} in the model check`)
  return parts.join(' · ')
}

function tokens(n: number): string {
  return n >= 1_000_000 ? `${Number((n / 1_000_000).toFixed(1))}M` : `${Math.round(n / 1000)}K`
}

/** The picked model in full, under the select: on a phone the closed select cuts its option's text. */
export function pickedText(m: OpenRouterModel): string {
  const parts = [m.name, priceText(m)]
  parts.push(m.check ? `${m.check.passed}/${m.check.total} in the model check` : 'not in a model check yet')
  if (m.context_length) parts.push(`${tokens(m.context_length)} context`)
  return parts.join(' · ')
}

/** The option to show for the saved model: itself when listed, else Other (with the id in the text field). */
export function picked(models: OpenRouterModel[], saved: string): string {
  return models.some((m) => m.id === saved) ? saved : OTHER
}
