// The floating save bar of Settings (and later Dev): DESIGN.md §5.7. Sticky at the bottom of the page, it keeps
// Patch's corner clear. Only the message is a live region, so a screen reader hears "Unsaved changes" once.

export function SaveBar({ dirty, saving, saved, error, onSave, onDiscard }: {
  dirty: boolean
  saving: boolean
  saved: boolean // just saved: says so until the next edit
  error: string | null
  onSave: () => void
  onDiscard: () => void
}) {
  const message = error ?? (dirty ? 'Unsaved changes' : saved ? '✓ Changes saved' : 'All changes saved')
  const tone = error ? ' error' : dirty ? ' dirty' : saved ? ' ok' : ''
  // B50: nothing to say ("All changes saved", nothing done yet): a phone hides the bar (settings.css)
  const idle = !error && !dirty && !saved && !saving
  return (
    <div className={`save-bar${idle ? ' idle' : ''}`}>
      <output className={`save-message${tone}`}>{message}</output>
      <button type="button" onClick={onDiscard} disabled={!dirty || saving}>
        Discard
      </button>
      <button type="submit" className="primary" onClick={onSave} disabled={!dirty || saving}>
        {saving ? 'Saving…' : 'Save changes'}
      </button>
    </div>
  )
}
