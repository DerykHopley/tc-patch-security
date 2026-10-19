// A link to a card further down a page (/settings#requests, B38; /#recent-alerts, B50): bring the card into view and
// keep it there while the cards above it load.

/** Scroll to `el`, and again while the cards above it finish loading (they grow and push it down), until the person
 * scrolls or types themselves, or 3 s pass. Returns the clean-up. */
export function keepInView(el: HTMLElement | null, onDone: () => void): (() => void) | undefined {
  if (!el) return undefined
  const go = () => el.scrollIntoView({ block: 'start' })
  go()
  const watch = new ResizeObserver(go)
  watch.observe(document.body)
  const stop = () => {
    watch.disconnect()
    clearTimeout(timer)
    for (const e of ['wheel', 'touchstart', 'keydown', 'pointerdown']) window.removeEventListener(e, done)
  }
  const done = () => {
    stop()
    onDone()
  }
  const timer = setTimeout(done, 3000)
  for (const e of ['wheel', 'touchstart', 'keydown', 'pointerdown']) window.addEventListener(e, done, { once: true })
  return stop
}
