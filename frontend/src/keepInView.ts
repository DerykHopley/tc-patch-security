// A link to a card further down a page (/settings#requests, B38; /#recent-alerts, B50): bring the card into view and
// keep it there while the cards around it load.

/** Scroll to `el`, and again whenever anything that could move it changes size (the cards above it grow and push it
 * down; in a two-column layout the other column grows and the browser's scroll anchoring scrolls the page to keep
 * that column still), until the person scrolls or types themselves, or 3 s pass. Returns the clean-up. */
export function keepInView(el: HTMLElement | null, onDone: () => void): (() => void) | undefined {
  if (!el) return undefined
  const go = () => el.scrollIntoView({ block: 'start' })
  go()
  // ResizeObserver callbacks run after layout and before paint, so the card never shows out of place. Watching only
  // the body missed B56: on the dashboard at 1440px the right column (Recent alerts' own) sets the page's height, so
  // the charts on the left drawing late left the body alone while scroll anchoring moved the page by ~190px.
  const watch = new ResizeObserver(go)
  watch.observe(document.body)
  for (const box of layoutNeighbours(el)) watch.observe(box)
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

/** Every element whose size can move `el` or scroll the page around it: `el`, its ancestors and their siblings (a
 * sibling's size covers everything inside it). */
function layoutNeighbours(el: Element): Element[] {
  const boxes: Element[] = []
  for (let n: Element | null = el; n?.parentElement && n !== document.body; n = n.parentElement) {
    boxes.push(...n.parentElement.children)
  }
  return boxes
}
