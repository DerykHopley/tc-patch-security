// Sign-in setup (B31, #78): Clerk's URLs stay inside Patch, and which view the sign-in screen shows for the page's
// address. `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { CLERK_URLS, NOT_INVITED, signInView } from './signInView.ts'

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
    ['', '#/create/sso-callback?redirect_url=x'], // an SSO round trip finishing: Clerk's own step
    ['', '#/create/verify-email-address'],
    ['?__clerk_ticket=t&__clerk_status=sign_in', ''], // an invitation for an existing account: sign in
  ]) {
    assert.equal(signInView(at(search, hash)), 'sign-in', `${search}${hash}`)
  }
})

test('B31.7: an invitation link (a ticket in the address) opens the sign-up form', () => {
  assert.equal(signInView(at('?__clerk_ticket=t', '')), 'invitation')
  assert.equal(signInView(at('?__clerk_ticket=t&__clerk_status=sign_up', '')), 'invitation')
  assert.equal(signInView(at('?__clerk_ticket=t', '#/sso-callback')), 'invitation') // its SSO round trip
})

test('B31.8: a sign-up without an invitation is the not-invited message', () => {
  assert.equal(signInView(at('', '#/create')), 'not-invited')
  assert.equal(signInView(at('', '#/create/')), 'not-invited')
  assert.equal(signInView(at('', '#/create?redirect_url=x')), 'not-invited')
  assert.equal(signInView(at('', '#/create?__clerk_ticket=t')), 'sign-in') // Clerk carrying a ticket: its step
  assert.equal(NOT_INVITED, "This account isn't invited to Patch. Ask the owner for an invitation.")
})
