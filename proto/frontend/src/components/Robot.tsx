// Patch, the robot mascot of the Playful design (D5). An original drawing: round body, visor face, floating hands.
// Moods: idle (bobs and blinks), thinking (eyes scan, antenna blinks), happy (smiling eyes, waves), alert (wide eyes).
import { useId } from "react";

export type Mood = "idle" | "thinking" | "happy" | "alert";

export function Robot({ mood = "idle", size = 64, className = "" }: { mood?: Mood; size?: number; className?: string }) {
  // Unique gradient ids: several robots can be on the page, and a hidden one's <defs> would break the others.
  const id = useId().replace(/:/g, "");
  return (
    <svg className={`robot mood-${mood} ${className}`} width={size} height={size * 1.08} viewBox="0 0 120 130" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}-body`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#d9defb" />
        </linearGradient>
        <radialGradient id={`${id}-eye`} cx="0.5" cy="0.4" r="0.6">
          <stop offset="0" stopColor="#e6fdff" />
          <stop offset="0.5" stopColor="#5cf2ff" />
          <stop offset="1" stopColor="#13b6d6" />
        </radialGradient>
      </defs>
      <ellipse className="bot-shadow" cx="60" cy="124" rx="26" ry="4.5" />
      <g className="bot-float">
        {/* antenna */}
        <line x1="60" y1="22" x2="60" y2="11" stroke="#8d97c9" strokeWidth="3" strokeLinecap="round" />
        <circle className="bot-light" cx="60" cy="8" r="5" />
        {/* hands */}
        <g className="bot-hand left"><rect x="2" y="70" width="14" height="22" rx="7" /></g>
        <g className="bot-hand right"><rect x="104" y="70" width="14" height="22" rx="7" /></g>
        {/* ears */}
        <rect x="15" y="44" width="9" height="24" rx="4.5" fill="#6c4cf5" />
        <rect x="96" y="44" width="9" height="24" rx="4.5" fill="#6c4cf5" />
        {/* body */}
        <rect x="22" y="20" width="76" height="86" rx="36" fill={`url(#${id}-body)`} stroke="#c3cbf3" strokeWidth="2" />
        {/* visor */}
        <rect x="31" y="33" width="58" height="34" rx="17" fill="#23265a" />
        <rect x="36" y="36" width="20" height="4" rx="2" fill="#ffffff" opacity="0.18" />
        {/* eyes */}
        <g className="bot-eyes">
          {mood === "happy" ? (
            <>
              <path d="M41 54 q7 -9 14 0" />
              <path d="M65 54 q7 -9 14 0" />
            </>
          ) : mood === "alert" ? (
            <>
              <circle cx="48" cy="50" r="8" fill={`url(#${id}-eye)`} />
              <circle cx="72" cy="50" r="8" fill={`url(#${id}-eye)`} />
            </>
          ) : (
            <>
              <rect x="42" y="42" width="12" height="16" rx="6" fill={`url(#${id}-eye)`} />
              <rect x="66" y="42" width="12" height="16" rx="6" fill={`url(#${id}-eye)`} />
            </>
          )}
        </g>
        {/* chest lights */}
        <circle className="bot-dot d1" cx="50" cy="82" r="3" />
        <circle className="bot-dot d2" cx="60" cy="82" r="3" />
        <circle className="bot-dot d3" cx="70" cy="82" r="3" />
        {/* thruster */}
        <path d="M46 105 h28 l-4 8 h-20 z" fill="#c3cbf3" />
      </g>
    </svg>
  );
}
