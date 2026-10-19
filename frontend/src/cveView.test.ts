// The CVE view: the CVEs page's filters under one set of names in the URL, the /cves query and the page context.
// Round trips per filter: URL → view → URL, the /cves query, the page context → the chip's words. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  contextWords,
  cvesQuery,
  filtersLabel,
  productIds,
  viewFromSearch,
  viewToContext,
  viewToSearch,
} from './cveView.ts'

test('B44.5 the folded filters say how many are on: every filter that differs from the defaults', () => {
  assert.equal(filtersLabel({ status: 'open' }), 'Filters (0 on)') // the defaults: every watched product, open
  assert.equal(filtersLabel({ status: 'all' }), 'Filters (1 on)') // another status is a filter
  const five = viewFromSearch('?product=langflow,ollama&severity=HIGH&kev=1&since=2026-09-14&new=1')
  assert.equal(filtersLabel(five), 'Filters (5 on)')
  assert.equal(filtersLabel({ status: 'fixed', verdict: 'affected' }), 'Filters (2 on)')
})

/** One filter through every encoding: what the URL says, the view, the /cves query, the page context, the words. */
const ROUND_TRIPS = [
  { url: '', view: { status: 'open' }, query: '/cves?limit=25&offset=0', context: { status: 'open' }, words: [] },
  {
    url: '?product=langflow',
    view: { status: 'open', product: 'langflow' },
    query: '/cves?product=langflow&limit=25&offset=0',
    context: { product: 'langflow', status: 'open' },
    words: ['Langflow'],
  },
  {
    url: '?product=langflow,ollama', // several, from a dashboard link (A15b): the comma stays readable
    view: { status: 'open', product: 'langflow,ollama' },
    query: '/cves?product=langflow,ollama&limit=25&offset=0',
    context: { product: 'langflow,ollama', status: 'open' },
    words: ['Langflow'],
  },
  {
    url: '?severity=HIGH',
    view: { status: 'open', severity: 'HIGH' },
    query: '/cves?severity=HIGH&limit=25&offset=0',
    context: { severity: 'HIGH', status: 'open' },
    words: ['High or worse'],
  },
  {
    url: '?status=all',
    view: { status: 'all' },
    query: '/cves?status=all&limit=25&offset=0',
    context: { status: 'all' },
    words: ['All statuses'],
  },
  {
    url: '?status=not_affected',
    view: { status: 'not_affected' },
    query: '/cves?status=not_affected&limit=25&offset=0',
    context: { status: 'not_affected' },
    words: ['Not affected'],
  },
  {
    url: '?verdict=affected',
    view: { status: 'open', verdict: 'affected' },
    query: '/cves?verdict=affected&limit=25&offset=0',
    context: { status: 'open', verdict: 'affected' },
    words: ['Affected'],
  },
  {
    url: '?kev=1',
    view: { status: 'open', kev: true },
    query: '/cves?kev=1&limit=25&offset=0',
    context: { status: 'open', kev: true },
    words: ['In KEV'],
  },
  {
    url: '?since=2026-09-14',
    view: { status: 'open', since: '2026-09-14' },
    query: '/cves?since=2026-09-14&limit=25&offset=0',
    context: { status: 'open', since: '2026-09-14' },
    words: ['Since 2026-09-14'],
  },
  {
    url: '?new=1', // B05; B40: new and not seen yet
    view: { status: 'open', new: true },
    query: '/cves?new=1&limit=25&offset=0',
    context: { status: 'open', new: true },
    words: ['New, not seen yet'],
  },
] as const

for (const t of ROUND_TRIPS) {
  test(`the view round-trips: "${t.url || '(no filters)'}"`, () => {
    const view = viewFromSearch(t.url)
    assert.deepEqual(view, t.view)
    assert.equal(viewToSearch(view), t.url)
    assert.equal(cvesQuery(view, 25, 0), t.query)
    assert.deepEqual(viewToContext(view), t.context)
    assert.deepEqual(contextWords(viewToContext(view), 'product' in t.view ? 'Langflow' : undefined), t.words)
  })
}

test('every filter at once keeps one order in the URL, the query and the words', () => {
  const url = '?product=langflow&severity=CRITICAL&status=accepted&verdict=unknown&kev=1&since=2025-01-01&new=1'
  const view = viewFromSearch(url)
  assert.equal(viewToSearch(view), url)
  assert.equal(cvesQuery(view, 5, 10), `/cves${url}&limit=5&offset=10`)
  assert.deepEqual(contextWords({ ...viewToContext(view), cve: 'CVE-2025-3248' }, 'Langflow'), [
    'Langflow', 'Critical or worse', 'Accepted', 'Unknown', 'In KEV', 'Since 2025-01-01', 'New, not seen yet',
    'CVE-2025-3248',
  ])
})

test('malformed values are dropped: the URL is text from outside', () => {
  assert.deepEqual(viewFromSearch('?severity=HUGE&status=closed&kev=maybe&since=yesterday&verdict=maybe&new=yes'), { status: 'open' })
  assert.deepEqual(viewFromSearch('?product=lang%3Bflow'), { status: 'open' })
  assert.deepEqual(viewFromSearch('?severity=critical'), { status: 'open', severity: 'CRITICAL' })
})

test('one product pattern: ids checked one by one, without repeats', () => {
  assert.deepEqual(productIds('langflow,ollama,langflow'), ['langflow', 'ollama'])
  assert.deepEqual(productIds('langflow,lang;flow,Open WebUI'), ['langflow'])
  assert.deepEqual(productIds(''), [])
  assert.deepEqual(productIds('a'.repeat(40)), ['a'.repeat(40)]) // the backend's limit: 40 characters
  assert.deepEqual(productIds('a'.repeat(41)), [])
})
