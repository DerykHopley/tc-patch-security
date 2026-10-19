// Sign-in setup (B31, #78; open sign-up B38, #81): Clerk's URLs stay inside Patch, and which view the sign-in screen
// shows for the page's address. `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { CLERK_URLS, signInView } from './signInView.ts'

const at = (search: string, hash: string) => ({ search, hash })

test('B31.6: every URL Clerk is given is a path in Patch, never Clerk hosted page', () => {
  for (const [name, url] of Object.entries(CLERK_URLS)) {
    assert.match(url, /^\/(#\/.*)?$/, name) // "/" or "/#/…": this origin, the sign-in screen
  }
  assert.equal(CLERK_URLS.signInUrl, '/')
  assert.equal(CLERK_URLS.signUpUrl, '/#/create') // the sign-up steps inside Patch's <SignIn> (withSignUp)
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
