import type { ProductUsage } from '../api.ts'
import { Card } from './StatusCard.tsx'
import type { WatchlistDraft } from './useWatchlist.ts'
import { USAGE_LABEL, USAGES } from './Verdict.tsx'
import '../styles/watchlist.css'

// The Watchlist card of Settings (A15b, DESIGN.md §5.7): the products you use and, per ticked product, how you run
// it (A15): usage, your version (optional) and internet-facing. Saved with the page's save bar. The version is
// checked by the product's ecosystem on save; a product without version data says so, because a version won't help
// its verdict there. A rejected save shows its message here, in the card.

const VERSION_EXAMPLE: Record<'PyPI' | 'npm' | 'Go', string> = { PyPI: '0.3.27', npm: '3.1.0', Go: 'v0.12.3' }

export function WatchlistCard({ w }: { w: WatchlistDraft }) {
  const saved = w.saved
  // Every product, by name, so a product keeps its place when it's ticked; the ticked ones' fields in watch order.
  const all = saved ? saved.products.toSorted((a, b) => a.name.localeCompare(b.name, 'en')) : []
  const ticked = w.picked.flatMap((id) => saved?.products.find((p) => p.product === id) ?? [])

  return (
    <Card title="Watchlist" className="watchlist-card" anchor="watchlist">
      <p className="meta">The products you use. Alerts, the dashboard, the CVEs page and Patch count only these.</p>
      {!saved ? (
        <p className="meta">{w.error ?? 'Loading the watchlist…'}</p>
      ) : (
        <>
          <ul className="watchlist">
            {all.map((p) => (
              <li key={p.product}>
                <label>
                  <input
                    type="checkbox"
                    checked={w.picked.includes(p.product)}
                    onChange={(e) => w.toggle(p.product, e.target.checked)}
                  />
                  {p.name}
                </label>
              </li>
            ))}
          </ul>
          {ticked.length > 0 && (
            <>
              <p className="meta">How you run them: for the verdict (am I affected?) and who acts.</p>
              <div className="stack-fields">
                {ticked.map((p) => {
                  const f = w.fields[p.product]
                  if (!f) return null
                  return (
                    <fieldset key={p.product} className="product-fields">
                      <legend>{p.name}</legend>
                      <label>
                        Usage
                        <select
                          value={f.usage}
                          onChange={(e) => w.set(p.product, { usage: e.target.value as ProductUsage })}
                        >
                          {USAGES.map((u) => (
                            <option key={u} value={u}>
                              {USAGE_LABEL[u]}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="field-row">
                        <label>
                          Version
                          <input
                            type="text"
                            inputMode="text"
                            autoComplete="off"
                            spellCheck={false}
                            maxLength={40}
                            placeholder={p.ecosystem ? `e.g. ${VERSION_EXAMPLE[p.ecosystem]}` : 'optional'}
                            value={f.version ?? ''}
                            onChange={(e) => w.set(p.product, { version: e.target.value || null })}
                          />
                        </label>
                        <label className="check">
                          <input
                            type="checkbox"
                            checked={f.internet_facing}
                            onChange={(e) => w.set(p.product, { internet_facing: e.target.checked })}
                          />
                          Internet-facing
                        </label>
                      </div>
                      {p.coverage === 'none' && (
                        <p className="meta field-note">No version data for {p.name}, so its verdicts stay unknown.</p>
                      )}
                      {p.coverage === 'commits' && (
                        <p className="meta field-note">
                          {p.name} fixes are listed as only code commits, so its verdicts stay unknown.
                        </p>
                      )}
                    </fieldset>
                  )
                })}
              </div>
            </>
          )}
          {w.error && (
            <p role="alert" className="form-error">
              {w.error}
            </p>
          )}
        </>
      )}
    </Card>
  )
}
