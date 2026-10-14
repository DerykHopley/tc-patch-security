import type { KeyboardEvent, PointerEvent } from 'react'
import { maxPinWidth, PIN_WIDTH, type ChatLayout } from './useChatLayout.ts'

// The 6px divider between the page and the pinned chat (DESIGN.md §6.3): drag it, or focus it and use ← / → in 24px
// steps. ← widens the chat (the divider moves left). The width stays between 320px and 60% of the window.

// The chat's right edge, measured: the width is whatever lies between the pointer and that edge.
function widthAt(divider: HTMLElement, clientX: number): number {
  const chat = divider.nextElementSibling
  const right = chat ? chat.getBoundingClientRect().right : window.innerWidth
  return right - clientX - divider.offsetWidth / 2
}

function onPointerDown(e: PointerEvent<HTMLDivElement>) {
  e.preventDefault() // no text selection while dragging
  e.currentTarget.setPointerCapture(e.pointerId)
}

export function ChatDivider({ layout }: { layout: ChatLayout }) {
  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) layout.setWidth(widthAt(e.currentTarget, e.clientX))
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const step = e.key === 'ArrowLeft' ? PIN_WIDTH.step : e.key === 'ArrowRight' ? -PIN_WIDTH.step : 0
    if (!step) return
    e.preventDefault()
    layout.setWidth(layout.width + step)
  }

  return (
    // A focusable separator is ARIA's window splitter, its value the chat's width. An <hr> would be the static kind:
    // the lint rules then forbid the focus and handlers a splitter needs.
    <div
      className="chat-divider"
      // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the chat"
      aria-valuenow={layout.width}
      aria-valuemin={PIN_WIDTH.min}
      aria-valuemax={maxPinWidth()}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onKeyDown={onKeyDown}
    />
  )
}
