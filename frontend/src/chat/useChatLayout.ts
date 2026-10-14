import { useState } from 'react'
import { store } from '../storage.ts'

export const PIN_WIDTH = { default: 440, min: 320, step: 24, maxShare: 0.6 } // DESIGN.md §6.3

/** The widest the pinned chat may be: 60% of the window. */
export const maxPinWidth = () => Math.floor(window.innerWidth * PIN_WIDTH.maxShare)
export const clampPinWidth = (w: number) => Math.round(Math.min(Math.max(w, PIN_WIDTH.min), maxPinWidth()))

// Old links: `?layout=split` pins the chat; other `?layout=` values are ignored (DESIGN.md §11).
function startPinned(): boolean {
  if (new URLSearchParams(window.location.search).get('layout') === 'split') return true
  return store.get('pinned') === '1'
}

function startWidth(): number {
  const saved = Number(store.get('splitWidth'))
  return Number.isFinite(saved) && saved > 0 ? clampPinWidth(saved) : PIN_WIDTH.default
}

/**
 * Where the chat sits (DESIGN.md §6.2–§6.5): closed, the bubble, the enlarged bubble, or pinned beside the page.
 * Pinned and its width are remembered per browser; a pinned chat opens pinned after a reload.
 */
export function useChatLayout() {
  const [pinned, setPinnedState] = useState(startPinned)
  const [open, setOpen] = useState(pinned) // a pinned chat starts open
  const [expanded, setExpanded] = useState(false)
  const [width, setWidthState] = useState(startWidth)

  // Pin docks the chat beside the page; Unpin floats it back as the enlarged bubble. The chat stays open.
  function setPinned(p: boolean) {
    setPinnedState(p)
    store.set('pinned', p ? '1' : '0')
    if (!p) setExpanded(true)
    setOpen(true)
  }

  function setWidth(w: number) {
    const next = clampPinWidth(w)
    setWidthState(next)
    store.set('splitWidth', String(next))
  }

  return {
    open,
    expanded,
    pinned,
    docked: pinned && open, // pinned and showing: the page makes room for it
    width,
    setOpen,
    setPinned,
    setWidth,
    toggleExpanded: () => setExpanded((x) => !x),
  }
}

export type ChatLayout = ReturnType<typeof useChatLayout>
