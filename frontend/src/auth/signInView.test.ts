// Sign-in setup (B31, #78; open sign-up B38, #81): Clerk's URLs stay inside Patch, and which view the sign-in screen
// shows for the page's address. `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { CLERK_URLS, frontDoor, signInView } from './signInView.ts'

const at = (search: string, hash: string) => ({ search, hash })

test('B31.6: every URL Clerk is given is a path in Patch, never Clerk hosted page', () => {
  for (const [name, url] of Object.entries(CLERK_URLS)) {
    assert.match(url, /^\/(sign-in)?(#\/.*)?$/, name) // "/", "/sign-in" or "/sign-in#/…": this origin
  }
  assert.equal(CLERK_URLS.signInUrl, '/sign-in') // B42: the landing page is the front door, the form is here
  assert.equal(CLERK_URLS.signUpUrl, '/sign-in#/create') // the sign-up steps inside Patch's <SignIn> (withSignUp)
  assert.equal(CLERK_URLS.afterSignOutUrl, '/') // signed out: back to the landing page
  assert.equal(CLERK_URLS.signInFallbackRedirectUrl, '/') // signed in: the dashboard
})

test('B31.7: the sign-in form by default and on its own steps', () => {
  for (const [search, hash] of [
    ['', ''],
    ['', '#/'],
    ['', '#/factor-one'],
    ['', '#/sso-callback'],
    ['?__clerk_ticket=t', ''], // an old invitation link: no invitations any more (B38), so plain sign-in
  ]) {
    assert.equal(signInView(at(search, hash)), 'sign-in', `${search}${hash}`)
  }
})

test("B38.24: Clerk's sign-up steps (open sign-up) are the request-access view, never a refusal", () => {
  for (const hash of ['#/create', '#/create/', '#/create?redirect_url=x', '#/create/sso-callback',
    '#/create/verify-email-address', '#/create/continue']) {
    assert.equal(signInView(at('', hash)), 'sign-up', hash)
  }
})

// B42 (#80): what a signed-out visitor sees at an address. The landing page everywhere (an unknown address too, #96),
// except where the sign-in form lives: /sign-in, Clerk's own steps (a hash route, "#/…") and an old invitation link.
const door = (pathname: string, search = '', hash = '', clerk = { loaded: true, wasSignedIn: false }) =>
  frontDoor({ pathname, search, hash }, clerk)

test('B42.2 a signed-out visitor lands on the landing page, at any address', () => {
  for (const path of ['/', '/cves', '/cves/CVE-2025-3248', '/settings', '/about', '/nope', '/sign-in-not']) {
    assert.equal(door(path), 'landing', path)
  }
  assert.equal(door('/', '', '#cve=CVE-2025-3248'), 'landing') // an old alert link is not a Clerk step
  assert.equal(door('/', '?product=langflow'), 'landing')
})

test("B42.3 the sign-in screen at /sign-in, on Clerk's steps and for an old invitation link", () => {
  assert.equal(door('/sign-in'), 'sign-in')
  assert.equal(door('/sign-in/'), 'sign-in')
  assert.equal(door('/sign-in', '', '#/create'), 'sign-in') // Request access
  assert.equal(door('/sign-in', '', '#/sso-callback'), 'sign-in')
  assert.equal(door('/', '', '#/create'), 'sign-in') // the sign-up address before B42
  assert.equal(door('/', '', '#/factor-one'), 'sign-in')
  assert.equal(door('/', '?__clerk_ticket=t'), 'sign-in')
  assert.equal(door('/', '?__clerk_status=sign_up'), 'sign-in')
})

const loading = (wasSignedIn: boolean) => ({ loaded: false, wasSignedIn })

test('B42.4 while Clerk loads, a browser that was signed in waits instead of flashing the landing page', () => {
  assert.equal(door('/', '', '', loading(true)), 'wait')
  assert.equal(door('/cves', '', '', loading(true)), 'wait')
  assert.equal(door('/', '', '', loading(false)), 'landing') // a first visit: the landing page at once
  assert.equal(door('/sign-in', '', '', loading(true)), 'sign-in') // the form shows its own loading line
  assert.equal(door('/', '', '', { loaded: true, wasSignedIn: true }), 'landing') // loaded and signed out
})
