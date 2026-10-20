// The app's paths (A04b) and the page for one CVE (B35, #85): /cves/CVE-…. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { afterSignIn, alertLinkPath, cvePath, locate, signInTargetAt } from './route.ts'

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

// B60 (#107): a signed-out visitor's address, kept by the front door for after sign-in
const at = (pathname: string, search = '', hash = '') => ({ pathname, search, hash })

test('B60.4 the front door keeps an in-app address, with its query and hash', () => {
  assert.equal(signInTargetAt(at('/cves/CVE-2025-3248')), '/cves/CVE-2025-3248') // an alert's link
  assert.equal(signInTargetAt(at('/settings', '', '#requests')), '/settings#requests') // the access-request alert
  assert.equal(signInTargetAt(at('/cves', '?product=langflow')), '/cves?product=langflow')
  assert.equal(signInTargetAt(at('/', '?product=ollama')), '/?product=ollama') // a filtered dashboard
  assert.equal(signInTargetAt(at('/about')), '/about')
})

test('B60.4 an old alert link (#cve=…, any path) is kept as its CVE page', () => {
  assert.equal(signInTargetAt(at('/', '', '#cve=CVE-2024-8309')), '/cves/CVE-2024-8309')
  assert.equal(signInTargetAt(at('/settings', '', '#cve=cve-2024-8309')), '/cves/CVE-2024-8309')
})

test("B60.4 nothing to keep at \"/\", the sign-in form, Clerk's steps or an unknown address", () => {
  for (const [path, search, hash] of [['/', '', ''], ['/sign-in', '', ''], ['/sign-in', '', '#/create'],
    ['/', '', '#/sso-callback'], ['/cves/CVE-2025-3248', '', '#/factor-one'], ['/nope', '', ''],
    ['/sign-in/', '', '']]) {
    assert.equal(signInTargetAt(at(path, search, hash)), null, `${path}${search}${hash}`)
  }
})

test('B60.5 after sign-in the app follows the target from where Clerk lands without one: "/" or the form', () => {
  assert.equal(afterSignIn('/', '/cves/CVE-2025-3248'), '/cves/CVE-2025-3248')
  assert.equal(afterSignIn('/sign-in', '/cves/CVE-2025-3248'), '/cves/CVE-2025-3248')
  assert.equal(afterSignIn('/sign-in/', '/settings#requests'), '/settings#requests')
})

test('B60.5 no target, or an address of its own: the app stays where it is', () => {
  assert.equal(afterSignIn('/', null), null) // the dashboard, as before
  assert.equal(afterSignIn('/cves/CVE-2025-3248', '/cves/CVE-2025-3248'), null) // Clerk went there itself
  assert.equal(afterSignIn('/about', '/cves/CVE-2025-3248'), null) // the address bar wins
})
