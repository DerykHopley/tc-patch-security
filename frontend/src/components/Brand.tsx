import { ShieldIcon } from './Icons.tsx'

// The brand, one name everywhere (B32, #82): "Patch", with what he is as the small line under it. The sidebar, the
// loading screen and the sign-in screen all draw it from here, so the three can't drift apart again.
export function Brand({ className = '' }: { className?: string }) {
  return (
    <div className={`brand ${className}`.trim()}>
      <span className="brand-mark">
        <ShieldIcon />
      </span>
      <span className="brand-name">
        <span>Patch</span>
        <small>LLM-security assistant</small>
      </span>
    </div>
  )
}
