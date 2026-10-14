import { useId } from 'react'
import { EXPLAIN_LEVELS, type ExplainLevel } from '../api.ts'

// The explain-level switch in the chat header (A19): three pills (radios), showing the saved level. Picking another
// applies it to the next question only; then it goes back to the saved level. It never saves: Settings does.
export function LevelSwitch({ saved, next, onPick }: {
  saved: ExplainLevel
  next: ExplainLevel | null
  onPick: (level: ExplainLevel | null) => void
}) {
  const name = useId()
  const current = next ?? saved
  return (
    <fieldset className="level-switch" aria-describedby={next ? `${name}-hint` : undefined}>
      <legend>Explain level</legend>
      <div className="level-pills">
        {EXPLAIN_LEVELS.map((lv) => (
          <label key={lv.id} title={lv.what}>
            <input
              type="radio"
              name={name}
              value={lv.id}
              checked={current === lv.id}
              onChange={() => onPick(lv.id === saved ? null : lv.id)}
            />
            {lv.label}
          </label>
        ))}
      </div>
      {next && (
        <span id={`${name}-hint`} className="level-hint">
          next question only
        </span>
      )}
    </fieldset>
  )
}
