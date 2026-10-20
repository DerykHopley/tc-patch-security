import { useState } from 'react'
import { setWelcomeShown, welcomeShown } from '../welcome.ts'

// Settings: brings back Patch's welcome banner after its ✕ (DESIGN.md §5.7, §5.8). A per-browser convenience, not a
// server setting, so it applies at once and stays outside the save bar.
export function WelcomeSwitch() {
  const [shown, setShown] = useState(welcomeShown)
  return (
    <div className="check-row switch-row">
      <input type="checkbox" id="welcome-shown" checked={shown} aria-describedby="welcome-shown-why"
        onChange={(e) => {
          setWelcomeShown(e.target.checked)
          setShown(e.target.checked)
        }} />
      <label htmlFor="welcome-shown">
        <strong>Show Patch's welcome on the dashboard</strong>
      </label>
      <span id="welcome-shown-why" className="meta">
        Remembered in this browser, not saved to the server. Applies at once.
      </span>
    </div>
  )
}
