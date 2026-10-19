// The app's paths (A04b) and the page for one CVE (B35, #85): /cves/CVE-…. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { alertLinkPath, cvePath, locate } from './route.ts'

test('B35.4 each page has its path', () => {
  assert.deepEqual(locate('/'), { page: 'dashboard', cve: null })
  assert.deepEqual(locate('/cves'), { page: 'cves', cve: null })
  assert.deepEqual(locate('/cves/'), { page: 'cves', cve: null })
  assert.deepEqual(locate('/settings'), { page: 'settings', cve: null })
})

test('B49.6 any other address is "Page not found", not the dashboard (#96 O1)', () => {
  assert.deepEqual(locate('/nowhere'), { page: 'notFound', cve: null })
  assert.deepEqual(locate('/nope/deeper'), { page: 'notFound', cve: null })
  assert.deepEqual(locate('/cves/CVE-2025-3248/more'), { page: 'notFound', cve: null })
  assert.deepEqual(locate('/Settings'), { page: 'notFound', cve: null }) // paths are lower case
})

test('B49.6 the sign-in address, signed in, is the app: Clerk may land a signed-in person there', () => {
  assert.deepEqual(locate('/sign-in'), { page: 'dashboard', cve: null })
})

test('B35.4 /cves/<id> is the page for one CVE, under CVEs, the id in upper case', () => {
  assert.deepEqual(locate('/cves/CVE-2025-3248'), { page: 'cves', cve: 'CVE-2025-3248' })
  assert.deepEqual(locate('/cves/cve-2025-3248/'), { page: 'cves', cve: 'CVE-2025-3248' })
})

test('B35.4 a malformed id still opens the CVE page, which says there is no such CVE', () => {
  assert.deepEqual(locate('/cves/not%20a%20cve'), { page: 'cves', cve: 'NOT A CVE' })
  assert.equal(locate(`/cves/${'x'.repeat(200)}`).cve?.length, 40) // cut short: it's only shown back
  assert.deepEqual(locate('/cves/%E0%A4%A'), { page: 'cves', cve: '%E0%A4%A' }) // not decodable: kept as typed
})

test('B42.1 /about is the About page (the landing page inside the app)', () => {
  assert.deepEqual(locate('/about'), { page: 'about', cve: null })
  assert.deepEqual(locate('/about/'), { page: 'about', cve: null })
})

test('B35.4 cvePath links to the CVE page', () => {
  assert.equal(cvePath('CVE-2025-3248'), '/cves/CVE-2025-3248')
  assert.equal(cvePath('cve-2025-3248'), '/cves/CVE-2025-3248')
})

test('B35.5 an old alert link (#cve=…) opens the CVE page instead of a banner', () => {
  assert.equal(alertLinkPath('#cve=CVE-2024-8309'), '/cves/CVE-2024-8309')
  assert.equal(alertLinkPath('#cve=cve-2024-8309'), '/cves/CVE-2024-8309')
  assert.equal(alertLinkPath(''), null)
  assert.equal(alertLinkPath('#schedule'), null)
  assert.equal(alertLinkPath('#cve=<img src=x onerror=alert(1)>'), null) // text from outside: ids only
})
