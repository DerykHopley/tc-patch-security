// B38 (#81): the Connected accounts card, on a fake Clerk user. `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { accountDetail, canUnlink, linkAccount, linkRedirectUrl, linkable, rows, type ClerkAccount, type ClerkUserLike } from './linkedAccounts.ts'

const account = (provider: string, over: Partial<ClerkAccount> = {}): ClerkAccount => ({
  id: `eac_${provider}`, provider, emailAddress: `${provider}@example.com`, username: undefined,
  verification: { status: 'verified', error: null }, destroy: async () => {}, ...over,
})

function user(over: Partial<ClerkUserLike> = {}): ClerkUserLike & { created: unknown[] } {
  const created: unknown[] = []
  return {
    passwordEnabled: true,
    externalAccounts: [],
    created,
    createExternalAccount: async (params) => {
      created.push(params)
      return { verification: { externalVerificationRedirectURL: new URL('https://discord.com/oauth2/authorize?x=1') } }
    },
    ...over,
  }
}

test('B38.30: the list shows linked accounts, and failed links with their reason', () => {
  const failed = account('google', { verification: { status: 'unverified', error: { longMessage: 'Access denied' } } })
  const pending = account('github', { verification: { status: 'unverified', error: null } })
  const shown = rows(user({ externalAccounts: [account('discord'), failed, pending] }))
  assert.deepEqual(shown.map((r) => [r.name, r.detail, r.error]), [
    ['Discord', 'discord@example.com', null],
    ['Google', 'google@example.com', 'Access denied'],
  ])
})

test('B38.31: only providers not linked yet can be linked', () => {
  assert.deepEqual(linkable(user({ externalAccounts: [account('discord')] })).map((p) => p.name), ['Google'])
  assert.deepEqual(linkable(user()).map((p) => p.name), ['Discord', 'Google'])
})

test('B38.32: link starts the provider flow, coming back to Settings on Patch', async () => {
  const u = user()
  const went: string[] = []
  await linkAccount(u, 'oauth_discord', 'https://patch.example', (url) => went.push(url))
  assert.deepEqual(u.created, [{ strategy: 'oauth_discord', redirectUrl: 'https://patch.example/settings#connected-accounts' }])
  assert.deepEqual(went, ['https://discord.com/oauth2/authorize?x=1'])
  assert.equal(linkRedirectUrl('http://localhost:5173'), 'http://localhost:5173/settings#connected-accounts')
})

test('B38.32: a link without a provider address fails plainly, and goes nowhere', async () => {
  const u = user({ createExternalAccount: async () => ({ verification: null }) })
  const went: string[] = []
  await assert.rejects(linkAccount(u, 'oauth_google', 'https://patch.example', (url) => went.push(url)),
    /didn't give an address/)
  assert.deepEqual(went, [])
})

test('B38.33: unlinking is refused for the last way to sign in', () => {
  const discord = account('discord')
  // a password and Discord: either can go
  assert.equal(canUnlink(user({ externalAccounts: [discord] }), discord), true)
  // Discord only, no password: it's the last way in
  assert.equal(canUnlink(user({ passwordEnabled: false, externalAccounts: [discord] }), discord), false)
  // two providers, no password: one can go
  const google = account('google')
  assert.equal(canUnlink(user({ passwordEnabled: false, externalAccounts: [discord, google] }), discord), true)
  // a failed link isn't a way in: it doesn't count
  const failed = account('google', { verification: { status: 'unverified', error: { longMessage: 'x' } } })
  assert.equal(canUnlink(user({ passwordEnabled: false, externalAccounts: [discord, failed] }), discord), false)
  assert.equal(canUnlink(user({ passwordEnabled: false, externalAccounts: [discord, failed] }), failed), true)
})

test('F154.2: hidden by default, an account shows no email or username, only that its details are hidden', () => {
  const [discord] = rows(user({ externalAccounts: [account('discord', { username: 'deryk#1' })] }))
  assert.equal(accountDetail(discord, false), 'Details hidden')
  assert.equal(accountDetail(discord, true), 'deryk#1')
})
