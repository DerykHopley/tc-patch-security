import { useCallback, useEffect, useState } from 'react'
import { getWatchlist, setWatchlist, type ProductFields, type Watchlist } from '../api.ts'
import { announceWatchlistChanged, useWatchlistChanged } from '../watchlistEvents.ts'

// The watchlist as a draft for the Settings card (A15b): load it, tick and untick products, set each one's usage,
// version and internet-facing, then save or discard with the page's save bar. A change made elsewhere (Patch's
// update_watchlist) loads again at once; unsaved picks stay as they are.

export type Fields = Record<string, ProductFields>

const DEFAULT_FIELDS = (product: string): ProductFields =>
  ({ product, usage: 'self_hosted', version: null, internet_facing: false })

function fieldsOf(w: Watchlist): Fields {
  return Object.fromEntries(
    w.products.map((p) => [
      p.product,
      { product: p.product, usage: p.usage, version: p.version, internet_facing: p.internet_facing },
    ]),
  )
}

const message = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong. Try again.')

export function useWatchlist() {
  const [saved, setSaved] = useState<Watchlist | null>(null)
  const [picked, setPicked] = useState<string[]>([])
  const [fields, setFields] = useState<Fields>({})
  const [saving, setSaving] = useState(false)
  const [justSaved, setJustSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const savedFields = saved ? fieldsOf(saved) : {}
  const dirty =
    !!saved &&
    (picked.toSorted().join() !== saved.watchlist.toSorted().join() ||
      picked.some((id) => JSON.stringify(fields[id]) !== JSON.stringify(savedFields[id])))

  const take = useCallback((w: Watchlist) => {
    setSaved(w)
    setPicked(w.watchlist)
    setFields(fieldsOf(w))
  }, [])

  /** Loads the saved watchlist. `keepDraft`: unsaved picks stay (a change from elsewhere moves only what's saved). */
  const reload = useCallback(
    (keepDraft = false, current: () => boolean = () => true) => {
      getWatchlist().then(
        (w) => {
          if (!current()) return
          if (keepDraft) setSaved(w)
          else take(w)
        },
        (e: unknown) => current() && setError(message(e)),
      )
    },
    [take],
  )
  // The first load drops its answer once its effect is cleaned up: in development React runs the effect twice, and
  // the late answer reset the picks made since the first (the Dev page's race, CI run 38847853994).
  useEffect(() => {
    let live = true
    reload(false, () => live)
    return () => {
      live = false
    }
  }, [reload])
  useWatchlistChanged(() => reload(dirty))

  function edited() {
    setJustSaved(false)
  }

  function toggle(id: string, on: boolean) {
    setPicked((p) => (on ? [...p.filter((x) => x !== id), id] : p.filter((x) => x !== id)))
    edited()
  }

  function set(id: string, patch: Partial<ProductFields>) {
    setFields((f) => ({ ...f, [id]: { ...(f[id] ?? DEFAULT_FIELDS(id)), ...patch } }))
    edited()
  }

  /** Saves the draft; a rejected value (an unknown product, a version that doesn't fit) comes back as `error`. */
  async function save(): Promise<boolean> {
    setSaving(true)
    setError(null)
    try {
      take(await setWatchlist(picked.map((id) => fields[id] ?? DEFAULT_FIELDS(id))))
      setJustSaved(true)
      announceWatchlistChanged() // the dashboard and the chat's view of it follow
      return true
    } catch (e) {
      setError(message(e))
      return false
    } finally {
      setSaving(false)
    }
  }

  function discard() {
    if (saved) take(saved)
    setError(null)
  }

  return { saved, picked, fields, dirty, saving, justSaved, error, toggle, set, save, discard, reload }
}

export type WatchlistDraft = ReturnType<typeof useWatchlist>
