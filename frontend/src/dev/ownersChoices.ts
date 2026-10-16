import type { DevSettings } from '../api.ts'

// The owner's Dev page choices as anyone else reads them (B29): label and value pairs, in the editable form's order
// and with its labels, so the owner and an invited user name each choice the same way.

export type Choice = [label: string, value: string]

const PROVIDER = { fake: 'FakeLLM (scripted)', openrouter: 'OpenRouter', local: 'Local model' }

export function modelChoices(d: DevSettings): Choice[] {
  const choices: Choice[] = [['Who answers', PROVIDER[d.provider]]]
  if (d.provider === 'fake') return choices // scripted: model and temperature don't apply
  if (d.provider === 'openrouter') choices.push(['Model', d.openrouter_model])
  else choices.push(['Model', d.local_model || 'none chosen'], ['Server URL', d.local_url])
  choices.push(['Temperature', d.temperature.toFixed(1)])
  return choices
}

const onOff = (v: boolean) => (v ? 'on' : 'off')

export function searchChoices(d: DevSettings): Choice[] {
  return [
    ['Max agent steps', String(d.max_steps)],
    ['Sources per search', String(d.top_n)],
    ['Results per query', String(d.per_query_k)],
    ['Chunks per document', String(d.per_doc_cap)],
    ['RRF constant k', String(d.rrf_k)],
    ['Keyword vs vector', d.keyword_weight.toFixed(2)],
    ['Multi-query rewrites', onOff(d.use_rewrites)],
    ['Self-query filters', onOff(d.use_filters)],
  ]
}
