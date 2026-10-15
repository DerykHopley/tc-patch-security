// Patch's pose: which of a mood's four animations he shows (DESIGN.md §8.3). Run with `npm test` (node --test).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { nextPose, pickPose } from './patchPose.ts'

/** A random source that returns the given values in turn, like Math.random but known. */
function sequence(...values: number[]): () => number {
  let i = 0
  return () => values[i++ % values.length]
}

test('the injected random source picks a known variant: one quarter of the range each', () => {
  assert.equal(pickPose('happy', () => 0).variant, 'bounce')
  assert.equal(pickPose('happy', () => 0.3).variant, 'spin')
  assert.equal(pickPose('happy', () => 0.5).variant, 'dance')
  assert.equal(pickPose('happy', () => 0.999).variant, 'hearts')
  assert.deepEqual(pickPose('alert', () => 0.6), { mood: 'alert', variant: 'siren' })
})

test('every mood has its four variants, in the canvas order A to D', () => {
  const all = (['idle', 'thinking', 'happy', 'alert'] as const).map((mood) =>
    [0, 0.25, 0.5, 0.75].map((r) => pickPose(mood, () => r).variant),
  )
  assert.deepEqual(all, [
    ['float', 'breathe', 'look', 'hop'],
    ['scan', 'typing', 'ponder', 'radar'],
    ['bounce', 'spin', 'dance', 'hearts'],
    ['shake', 'startle', 'siren', 'pop'],
  ])
})

test('the pick changes only when the mood changes, never while Patch stays in it', () => {
  const random = sequence(0.1, 0.6, 0.9, 0.3)
  let pose = pickPose('idle', random) // 0.1: float
  assert.equal(pose.variant, 'float')
  const same = nextPose(pose, 'idle', random) // a re-render in the same mood: no new pick
  assert.equal(same, pose)
  pose = nextPose(pose, 'thinking', random) // 0.6: ponder
  assert.deepEqual(pose, { mood: 'thinking', variant: 'ponder' })
  assert.equal(nextPose(pose, 'thinking', random), pose)
  assert.equal(nextPose(pose, 'thinking', random), pose)
  pose = nextPose(pose, 'happy', random) // 0.9: the random source moved on only once per mood change
  assert.deepEqual(pose, { mood: 'happy', variant: 'hearts' })
  pose = nextPose(pose, 'idle', random) // re-entering idle picks again: 0.3, breathe
  assert.deepEqual(pose, { mood: 'idle', variant: 'breathe' })
})
