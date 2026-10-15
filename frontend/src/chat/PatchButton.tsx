import type { Ref } from 'react'
import { Robot, type Mood, type Variant } from '../components/Robot.tsx'

// Patch's button (DESIGN.md §6.1): Patch (58px) stands in front of a pill, overlapping its top edge. While the
// chat is open he steps off and the pill turns purple with a white ✕.
export function PatchButton({ open, mood, variant, unread, onClick, ref }: {
  open: boolean
  mood: Mood
  variant: Variant
  unread: boolean
  onClick: () => void
  ref?: Ref<HTMLButtonElement>
}) {
  return (
    <button
      ref={ref}
      type="button"
      className={`patch-fab${open ? ' open' : ''}`}
      aria-label={open ? 'Close the chat' : 'Ask Patch'}
      aria-expanded={open}
      aria-describedby={unread ? 'patch-unread' : undefined}
      onClick={onClick}
    >
      {!open && <Robot size={58} mood={mood} variant={variant} />}
      <span className="patch-pill" aria-hidden="true">
        {open && '✕'}
      </span>
      {unread && (
        <span className="unread-dot">
          <span id="patch-unread" className="visually-hidden">
            New answer
          </span>
        </span>
      )}
    </button>
  )
}
