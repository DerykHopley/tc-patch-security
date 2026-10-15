// The OpenRouter model dropdown's words and its pick (A11.10). Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { OpenRouterModel } from '../api.ts'
import { OTHER, optionText, picked, pickedText, priceText } from './openRouterOptions.ts'

function model(id: string, input: number | null, output: number | null, check: OpenRouterModel['check'] = null) {
  return { id, name: id, input_per_m: input, output_per_m: output, context_length: 200000, check }
}

test('prices per million tokens, in dollars with cents', () => {
  assert.equal(priceText(model('a/b', 0.1, 0.5)), '$0.10 / $0.50 per M tokens')
  assert.equal(priceText(model('a/b', 1, 5)), '$1.00 / $5.00 per M tokens')
})

test('a price under a cent keeps its digits, and free says free', () => {
  assert.equal(priceText(model('a/b', 0.025, 0.004)), '$0.025 / $0.004 per M tokens')
  assert.equal(priceText(model('a/b', 0, 0)), 'free')
})

test('a variable price is unknown, never $0', () => {
  assert.equal(priceText(model('a/b', null, null)), 'price unknown')
  assert.equal(priceText(model('a/b', 0.1, null)), '$0.10 / ? per M tokens')
})

test('an option: id, the default marked, price, then the model-check score when there is one', () => {
  const haiku = model('anthropic/claude-haiku-5.5', 1, 5, { passed: 12, total: 14, run: 'r1' })
  assert.equal(optionText(haiku, 'anthropic/claude-haiku-5.5'),
    'anthropic/claude-haiku-5.5 (default) · $1.00 / $5.00 per M tokens · 12/14 in the model check')
  assert.equal(optionText(model('openai/gpt-5-mini', 0.25, 2), 'anthropic/claude-haiku-5.5'),
    'openai/gpt-5-mini · $0.25 / $2.00 per M tokens')
})

test('the picked model under the select: name, price, score and context, readable when the select cuts its text', () => {
  const haiku = { ...model('anthropic/claude-haiku-5.5', 1, 5, { passed: 12, total: 14, run: 'r1' }),
    name: 'Anthropic: Claude Haiku 5.5' }
  assert.equal(pickedText(haiku),
    'Anthropic: Claude Haiku 5.5 · $1.00 / $5.00 per M tokens · 12/14 in the model check · 200K context')
  assert.equal(pickedText({ ...model('a/b', null, null), context_length: null }), 'a/b · price unknown · not in a model check yet')
})

test('the saved model is picked when listed; otherwise Other, so the saved id is never changed silently', () => {
  const list = [model('a/listed', 1, 1)]
  assert.equal(picked(list, 'a/listed'), 'a/listed')
  assert.equal(picked(list, 'z/not-listed'), OTHER)
})
