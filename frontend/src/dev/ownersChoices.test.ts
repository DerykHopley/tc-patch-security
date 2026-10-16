// The owner's Dev page choices as anyone else reads them (B29). Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { DevSettings } from '../api.ts'
import { modelChoices, searchChoices } from './ownersChoices.ts'

const saved: DevSettings = {
  provider: 'openrouter',
  openrouter_model: 'qwen/qwen3-235b-a22b-2507',
  local_url: 'http://localhost:11434/v1',
  local_model: '',
  temperature: 0.2,
  max_steps: 4,
  top_n: 5,
  per_query_k: 10,
  per_doc_cap: 2,
  rrf_k: 60,
  keyword_weight: 0.5,
  use_rewrites: true,
  use_filters: false,
}

test('B29.4 the model choices name who answers, the model and the temperature', () => {
  assert.deepEqual(modelChoices(saved), [
    ['Who answers', 'OpenRouter'],
    ['Model', 'qwen/qwen3-235b-a22b-2507'],
    ['Temperature', '0.2'],
  ])
})

test('B29.4 a local model names its server; FakeLLM has no model or temperature', () => {
  assert.deepEqual(modelChoices({ ...saved, provider: 'local', local_model: 'qwen3:8b' }), [
    ['Who answers', 'Local model'],
    ['Model', 'qwen3:8b'],
    ['Server URL', 'http://localhost:11434/v1'],
    ['Temperature', '0.2'],
  ])
  assert.deepEqual(modelChoices({ ...saved, provider: 'fake' }), [['Who answers', 'FakeLLM (scripted)']])
})

test('B29.4 the search choices use the editable form\'s labels, switches as on or off', () => {
  assert.deepEqual(searchChoices(saved), [
    ['Max agent steps', '4'],
    ['Sources per search', '5'],
    ['Results per query', '10'],
    ['Chunks per document', '2'],
    ['RRF constant k', '60'],
    ['Keyword vs vector', '0.50'],
    ['Multi-query rewrites', 'on'],
    ['Self-query filters', 'off'],
  ])
})
