// Buttons on tool cards (B24): which buttons a card offers, and where "Open in CVEs page" goes. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { changeButtons, fixFirstHref, refineButtons } from './cardActions.ts'

test('B24.4 "Open in CVEs page" carries the fix-first card\'s filters, open CVEs only', () => {
  assert.equal(fixFirstHref({}), '/cves')
  assert.equal(fixFirstHref({ product: 'langflow', severity: 'HIGH', kev: true }), '/cves?product=langflow&severity=HIGH&kev=1')
  assert.equal(fixFirstHref({ verdict: 'affected', since: '2026-09-13' }), '/cves?verdict=affected&since=2026-09-13')
})

test('B24.5 a CVE card offers only the changes that would change something', () => {
  assert.deepEqual(changeButtons('open'), ['set_version', 'not_affected'])
  assert.deepEqual(changeButtons('not_watched'), ['watch'])
  assert.deepEqual(changeButtons('fixed'), ['set_version'])
  assert.deepEqual(changeButtons('not_affected'), ['set_version'])
  assert.deepEqual(changeButtons('accepted'), ['set_version', 'not_affected'])
})

test('B24.6 the search card offers the refines not applied yet, and keeps what was applied', () => {
  assert.deepEqual(
    refineButtons([]).map((b) => [b.label, b.filters]),
    [
      ['Show only CVEs', ['only_cves']],
      ['Only critical', ['only_critical']],
    ],
  )
  assert.deepEqual(
    refineButtons(['only_cves']).map((b) => [b.label, b.filters]),
    [['Only critical', ['only_cves', 'only_critical']]],
  )
  assert.deepEqual(refineButtons(['only_cves', 'only_critical']), [])
})
