import { useEffect, useRef, useState } from 'react'
import { devOpenRouterModels, type OpenRouterModel } from '../api.ts'
import { OTHER, optionText, picked, pickedText } from './openRouterOptions.ts'

// The OpenRouter model (A11.10, DESIGN.md §5.6.1): a dropdown of the models this key may use (OpenRouter's guardrail
// allow-list, tool-capable only), with prices and the model-check score at the point of choice. "Other…" opens a text
// field for an id not listed. With no list (no key, OpenRouter unreachable) it falls back to the text field and says
// why. The value saves with the rest of the Dev page; the backend validates it as before.

type Listing = { models: OpenRouterModel[]; reason: string | null }

export function OpenRouterModelField({ value, defaultId, onChange }: {
  value: string
  defaultId: string
  onChange: (id: string) => void
}) {
  const [listing, setListing] = useState<Listing | null>(null) // null while loading
  const [choseOther, setChoseOther] = useState(false)
  const otherRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    devOpenRouterModels().then(setListing, (e: Error) => setListing({ models: [], reason: e.message }))
  }, [])

  useEffect(() => {
    if (choseOther) otherRef.current?.focus() // picked Other: straight to typing
  }, [choseOther])

  if (!listing) {
    return (
      <div className="field-row">
        <label htmlFor="dev-or-model">OpenRouter model</label>
        <select id="dev-or-model" className="or-select" disabled aria-busy="true">
          <option>Loading the models this key may use…</option>
        </select>
      </div>
    )
  }

  if (listing.models.length === 0) {
    return (
      <>
        <div className="field-row">
          <label htmlFor="dev-or-model">OpenRouter model</label>
          <input id="dev-or-model" className="mono-input" value={value} spellCheck={false}
            onChange={(e) => onChange(e.target.value.trim())} />
        </div>
        <p className="meta" role="note">
          {listing.reason
            ? `Couldn't list the models: ${listing.reason} Type a model id instead.`
            : 'OpenRouter lists no models with tools for this key. Type a model id instead.'}
        </p>
      </>
    )
  }

  const listed = picked(listing.models, value) !== OTHER
  const selected = choseOther || !listed ? OTHER : value
  const current = listing.models.find((m) => m.id === selected)

  function pick(id: string) {
    if (id === OTHER) {
      setChoseOther(true) // keeps the current id in the text field: nothing changes until you type
      return
    }
    setChoseOther(false)
    onChange(id)
  }

  return (
    <>
      <div className="field-row">
        <label htmlFor="dev-or-model">OpenRouter model</label>
        <select id="dev-or-model" className="or-select" value={selected} onChange={(e) => pick(e.target.value)}
          aria-describedby={current ? 'dev-or-picked' : undefined}>
          {listing.models.map((m) => (
            <option key={m.id} value={m.id} title={m.name}>
              {optionText(m, defaultId)}
            </option>
          ))}
          <option value={OTHER}>Other…</option>
        </select>
      </div>
      {current && (
        <p id="dev-or-picked" className="meta or-picked">
          {pickedText(current)}
        </p>
      )}
      {selected === OTHER && (
        <>
          <div className="field-row">
            <label htmlFor="dev-or-other">Model id</label>
            <input id="dev-or-other" ref={otherRef} className="mono-input" value={value} spellCheck={false}
              placeholder="e.g. mistralai/mistral-small" onChange={(e) => onChange(e.target.value.trim())} />
          </div>
          {value && !listed && (
            <p className="meta">Not in the list for this key: OpenRouter's guardrail may refuse it.</p>
          )}
        </>
      )}
      <p className="meta">
        The models this key may use that take tools, cheapest input first. Prices per million tokens, input / output.
      </p>
    </>
  )
}
