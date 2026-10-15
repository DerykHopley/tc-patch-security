// Patch's pose: his mood and which of its four animations he shows (DESIGN.md §8.3). The four per mood are the
// options A to D of the "Robot Style Explorations" canvas (docs/design/patch/). Pure, so it's tested without React.

export type Mood = 'idle' | 'thinking' | 'happy' | 'alert'

export const VARIANTS = {
  idle: ['float', 'breathe', 'look', 'hop'],
  thinking: ['scan', 'typing', 'ponder', 'radar'],
  happy: ['bounce', 'spin', 'dance', 'hearts'],
  alert: ['shake', 'startle', 'siren', 'pop'],
} as const

export type Variant = (typeof VARIANTS)[Mood][number]
export type Pose = { mood: Mood; variant: Variant }

/** Like Math.random: a number in [0, 1). Injected so tests pick a known variant. */
export type Random = () => number

/** One of the mood's four variants, at random: each gets a quarter of the range. */
export function pickPose(mood: Mood, random: Random): Pose {
  const options = VARIANTS[mood]
  const i = Math.min(options.length - 1, Math.floor(random() * options.length))
  return { mood, variant: options[i] }
}

/** The pose for `mood`: a new pick when Patch enters it, the same pose (same object) while he stays in it. */
export function nextPose(prev: Pose, mood: Mood, random: Random): Pose {
  return prev.mood === mood ? prev : pickPose(mood, random)
}
