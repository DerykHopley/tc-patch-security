// The sticky save bar for the settings page and the dev panel.
export function SaveBar({ dirty, saving, savedAt, error, onSave, onDiscard }: {
  dirty: boolean; saving: boolean; savedAt: number | null; error: string | null; onSave: () => void; onDiscard: () => void;
}) {
  return (
    <div className="save-bar" role="status">
      {error ? <span className="save-error">{error}</span>
        : dirty ? <span>Unsaved changes</span>
        : savedAt ? <span className="saved">✓ Saved</span>
        : <span className="muted">All changes saved</span>}
      <button type="button" onClick={onDiscard} disabled={!dirty || saving}>Discard</button>
      <button type="submit" onClick={onSave} disabled={!dirty || saving}>{saving ? "Saving…" : "Save changes"}</button>
    </div>
  );
}
