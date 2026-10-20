// B28: where live data comes from, as the Data card and the freshness card say it. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { dataSources, feedsLine, freshnessFeedsWarning } from './freshness.ts'

test('B28.6 the Data card names the real feeds, or warns about the made-up test data', () => {
  assert.deepEqual(feedsLine('real'), { tone: 'ok', text: 'Live: NVD, CISA KEV, EPSS and OSV.dev' })
  assert.deepEqual(feedsLine('fake'), { tone: 'warn', text: 'Live: the made-up test data, not the real feeds' })
})

test('B50.7 the Data card names all six sources, never a setting', () => {
  for (const mode of ['snapshot', 'live'] as const) {
    for (const name of ['OWASP', 'MITRE ATLAS', 'NVD', 'CISA KEV', 'EPSS', 'OSV.dev']) {
      assert.ok(dataSources(mode).includes(name), `${mode}: ${name}`)
    }
  }
  assert.doesNotMatch(feedsLine('fake').text, /FEEDS|=/) // B50: the setting's name is in README.md
})

test('B28.6 the freshness card warns only in live mode on the fake feeds, and only the owner (feeds set)', () => {
  assert.equal(freshnessFeedsWarning({ mode: 'live', last_checked: null, feeds: 'fake' }),
    'Live: the made-up test data, not the real feeds')
  assert.equal(freshnessFeedsWarning({ mode: 'live', last_checked: null, feeds: 'real' }), null)
  assert.equal(freshnessFeedsWarning({ mode: 'snapshot', last_checked: null, feeds: 'fake' }), null)
  assert.equal(freshnessFeedsWarning({ mode: 'live', last_checked: null, feeds: null }), null) // not the owner
  assert.equal(freshnessFeedsWarning({ mode: 'live', last_checked: null }), null)
})
