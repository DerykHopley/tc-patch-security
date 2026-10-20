// Settings' "Start over" card (B50, #95): what a reset deletes and keeps, by role. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { resetDeletes, resetKeeps, START_OVER_BUTTON } from './startOver.ts'

test('B50.6 the reset says it deletes the decision history, for everyone', () => {
  assert.equal(START_OVER_BUTTON, 'Reset all my data') // no longer "demo data": it is the user's own
  for (const role of ['owner', 'viewer', 'trusted', 'reviewer'] as const) {
    assert.ok(resetDeletes(role).some((l) => l.includes('whole decision history')), role)
    assert.match(resetKeeps(role), /display name/)
  }
})

test("B50.6 the owner's reset also names everyone's Dev choices and the channels; a reviewer's their copy", () => {
  const owner = resetDeletes('owner')
  assert.ok(owner.some((l) => l.startsWith("The Dev page's choices: everyone's chat")))
  assert.ok(owner.some((l) => l.includes('alert channels')))
  assert.match(resetKeeps('owner'), /server settings/)
  assert.deepEqual(resetDeletes('reviewer').at(-1), 'Your own copy of the Dev settings')
  for (const role of ['viewer', 'trusted'] as const) {
    assert.equal(resetDeletes(role).length, 4)
    assert.ok(!resetDeletes(role).some((l) => /Dev|channel/.test(l)), role)
    assert.equal(resetKeeps(role), 'Kept: your display name.')
  }
})
