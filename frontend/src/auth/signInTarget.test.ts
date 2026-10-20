// The address a signed-out visitor asked for, kept for after sign-in (B60, #107). `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { clerkRedirects, keepTarget,readTarget, safeTarget, takeTarget, type TargetStorage } from './signInTarget.ts'

const ORIGIN = 'https://patch.example'

test('B60.1: a same-origin path is a target, with its query and hash', () => {
  assert.equal(safeTarget('/cves/CVE-2025-3248', ORIGIN), '/cves/CVE-2025-3248')
  assert.equal(safeTarget('/settings#requests', ORIGIN), '/settings#requests')
  assert.equal(safeTarget('/cves?product=langflow&kev=1', ORIGIN), '/cves?product=langflow&kev=1')
})

test('B60.2: anything that could leave Patch is refused (no open redirect)', () => {
  for (const bad of [
    'https://evil.example/cves', // a full URL, even ...
    `${ORIGIN}/cves`, // ... one on this origin: only paths are kept
    '//evil.example', // protocol-relative: another host
    '//evil.example/cves/CVE-2025-3248',
    '/\\evil.example', // browsers read "\" as "/": //evil.example
    '\\\\evil.example',
    '/\t/evil.example', // browsers drop tabs and newlines: //evil.example
    '/\n/evil.example',
    'javascript:alert(1)',
    ' /cves', // must start with "/"
    'cves/CVE-2025-3248',
    '',
    '/' + 'a'.repeat(3000), // too long to be one of Patch's addresses
  ]) {
    assert.equal(safeTarget(bad, ORIGIN), null, JSON.stringify(bad))
  }
})

test('B60.2: only text is a target', () => {
  for (const bad of [null, undefined, 42, { path: '/cves' }]) assert.equal(safeTarget(bad, ORIGIN), null)
})

/** A tab's sessionStorage, in memory. */
function tab(): TargetStorage & { items: Map<string, string> } {
  const items = new Map<string, string>()
  return {
    items,
    getItem: (k) => items.get(k) ?? null,
    setItem: (k, v) => void items.set(k, v),
    removeItem: (k) => void items.delete(k),
  }
}

const fail = () => { throw new Error('blocked') }
const blocked: TargetStorage = { getItem: fail, setItem: fail, removeItem: fail }

test('B60.3: a kept target is read until it is taken, then it is gone (used once)', () => {
  const s = tab()
  keepTarget('/cves/CVE-2025-3248', s, ORIGIN)
  assert.equal(readTarget(s, ORIGIN), '/cves/CVE-2025-3248')
  assert.equal(readTarget(s, ORIGIN), '/cves/CVE-2025-3248') // Clerk's form reads it on every render
  assert.equal(takeTarget(s, ORIGIN), '/cves/CVE-2025-3248')
  assert.equal(takeTarget(s, ORIGIN), null)
  assert.equal(readTarget(s, ORIGIN), null)
})

test('B60.3: no target (the visitor came to "/") forgets an older one', () => {
  const s = tab()
  keepTarget('/cves/CVE-2025-3248', s, ORIGIN)
  keepTarget(null, s, ORIGIN)
  assert.equal(takeTarget(s, ORIGIN), null)
})

test('B60.2: an unsafe target is never kept, and one written by other code is refused on reading', () => {
  const s = tab()
  keepTarget('//evil.example', s, ORIGIN)
  assert.equal(s.items.size, 0)
  s.items.set('signInTarget', 'https://evil.example/')
  assert.equal(readTarget(s, ORIGIN), null)
  assert.equal(takeTarget(s, ORIGIN), null)
  assert.equal(s.items.size, 0) // taken anyway: a bad value doesn't linger
})

test("B60.6: Clerk's form goes to the target after sign-in and after sign-up; with none, Clerk's own '/'", () => {
  assert.deepEqual(clerkRedirects('/cves/CVE-2025-3248'), {
    forceRedirectUrl: '/cves/CVE-2025-3248',
    signUpForceRedirectUrl: '/cves/CVE-2025-3248',
  })
  assert.deepEqual(clerkRedirects(null), {}) // CLERK_URLS' fallback, "/", as before
})

test('B60.3: blocked storage keeps nothing and never throws', () => {
  keepTarget('/cves/CVE-2025-3248', blocked, ORIGIN)
  assert.equal(readTarget(blocked, ORIGIN), null)
  assert.equal(takeTarget(blocked, ORIGIN), null)
  keepTarget('/cves/CVE-2025-3248', null, ORIGIN)
  assert.equal(takeTarget(null, ORIGIN), null)
})
