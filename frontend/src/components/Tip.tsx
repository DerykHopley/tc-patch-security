import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { placeTip } from '../tips.ts'
import '../styles/tip.css'

// A tooltip by mouse, keyboard and touch (B44, #94; DESIGN.md §5.17). A native `title` shows on mouse hover only: a
// keyboard or a phone never sees it. Here the anchor is a Tab stop and its words are its description
// (aria-describedby), and the bubble shows on:
//   - mouse: hover (it stays while the pointer moves onto the bubble, so it can be read and selected);
//   - keyboard: focus (only a keyboard focus, :focus-visible, so a mouse click doesn't leave it stuck open);
//   - touch: a tap opens it, a second tap or a tap elsewhere closes it.
// Esc closes it wherever the focus is. The bubble is drawn in <body> (a portal) at a fixed place, so the table's
// sideways-scroll box never clips it. It doesn't move or fade: nothing for reduced motion to stop.

type Place = { left: number; top: number; below: boolean }

let closeOpenTip: (() => void) | null = null // the tip on screen now, if any

export function Tip({ text, children, className = '', plain = false }: {
  text: string
  children: ReactNode
  className?: string // the anchor's own look (a chip, a heading)
  plain?: boolean // no dotted underline: the anchor already looks like a thing (a chip)
}) {
  const id = useId()
  const anchor = useRef<HTMLButtonElement>(null)
  const bubble = useRef<HTMLSpanElement>(null)
  const [hover, setHover] = useState(false)
  const [keyFocus, setKeyFocus] = useState(false)
  const [tapped, setTapped] = useState(false)
  const [place, setPlace] = useState<Place | null>(null)
  const pointer = useRef('mouse') // the last pointer's kind, from pointerdown
  const focusedBefore = useRef(false) // was the anchor focused before this tap?
  const leaving = useRef<number | undefined>(undefined)
  const open = hover || keyFocus || tapped

  const close = useCallback(() => {
    setHover(false)
    setKeyFocus(false)
    setTapped(false)
  }, [])

  const measure = useCallback(() => {
    if (!bubble.current || !anchor.current) return
    bubble.current.style.left = '0px' // measure at full width: near the right edge the old place would squeeze it
    const a = anchor.current.getBoundingClientRect()
    const b = bubble.current.getBoundingClientRect()
    setPlace(placeTip(a, b, { width: document.documentElement.clientWidth, height: window.innerHeight }))
  }, [])

  useLayoutEffect(() => {
    if (open) measure() // before the paint: the bubble never shows in the wrong place
  }, [open, measure])

  useEffect(() => {
    if (!open) return
    // One tip at a time: moving from one heading to the next never leaves two bubbles on the screen
    if (closeOpenTip && closeOpenTip !== close) closeOpenTip()
    closeOpenTip = close
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation() // Esc closes the tip, not the chat or a dialog behind it
      close()
    }
    window.addEventListener('keydown', onKey, true)
    window.addEventListener('scroll', measure, true)
    window.addEventListener('resize', measure)
    return () => {
      if (closeOpenTip === close) closeOpenTip = null
      window.removeEventListener('keydown', onKey, true)
      window.removeEventListener('scroll', measure, true)
      window.removeEventListener('resize', measure)
    }
  }, [open, close, measure])

  useEffect(() => () => window.clearTimeout(leaving.current), [])

  const enter = (e: React.PointerEvent) => {
    if (e.pointerType !== 'mouse') return
    window.clearTimeout(leaving.current)
    setHover(true)
  }
  // A short grace, so the pointer can cross the gap onto the bubble (WCAG 1.4.13: hoverable)
  const leave = (e: React.PointerEvent) => {
    if (e.pointerType !== 'mouse') return
    leaving.current = window.setTimeout(() => setHover(false), 150) // allowed: hover grace, not a test wait
  }

  return (
    <>
      {/* A button: a Tab stop that a tap and a screen reader both know, with its words as its description */}
      <button
        type="button"
        ref={anchor}
        className={`tip-anchor${plain ? ' plain' : ''} ${className}`.trim()}
        aria-describedby={id}
        onPointerEnter={enter}
        onPointerLeave={leave}
        onPointerDown={(e) => {
          pointer.current = e.pointerType
          focusedBefore.current = document.activeElement === anchor.current
        }}
        onClick={(e) => {
          // Touch and pen: the first tap opens, the next closes. A mouse has hover; a keyboard's Enter or Space
          // (detail 0) changes nothing, since the focus already shows it.
          if (e.detail === 0 || pointer.current === 'mouse') return
          setTapped(focusedBefore.current ? !open : true)
        }}
        onFocus={(e) => setKeyFocus(e.currentTarget.matches(':focus-visible'))}
        onBlur={() => {
          setKeyFocus(false)
          setTapped(false)
        }}
      >
        {children}
      </button>
      {createPortal(
        <span
          ref={bubble}
          id={id}
          role="tooltip"
          className={`tip${place?.below ? ' below' : ''}`}
          hidden={!open}
          style={open && place ? { left: place.left, top: place.top } : { left: 0, top: 0, visibility: 'hidden' }}
          onPointerEnter={enter}
          onPointerLeave={leave}
        >
          {text}
        </span>,
        document.body,
      )}
    </>
  )
}
