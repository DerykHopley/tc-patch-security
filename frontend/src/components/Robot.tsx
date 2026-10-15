// Patch, the squircle robot (DESIGN.md §8), from the "Robot Style Explorations" canvas (docs/design/patch/).
// Four moods, four animations each (A to D). Shapes, colours and timings are copied from the canvas; the
// animations are in styles/robot.css. Patch's colours are fixed: the same in light and dark mode.
// Parts outside the body (thought dots, sparkles, notes, hearts, the "!" badge, the siren beam) carry `bot-extra`,
// so the browser check can keep them clear of the controls around Patch.
import type { ReactNode } from 'react'
import { VARIANTS, type Mood, type Variant } from './patchPose.ts'

export type { Mood, Variant } from './patchPose.ts'

const BODY = '#9483FF'
const VISOR = '#2A2457'
const EYE = '#7FF0DD'
const LIGHT = '#FFC94D'
const CHEEK = '#FFB3CF'
const BLUSH = '#FF9EC0'
const HEART = '#FF6F91'
const WARN = '#FF6B8E'
const SIREN = '#FF4D6D'
const LILAC = '#B4A9FF'
const HEART_PATH = 'M8 14 C8 14 0 9 0 4 C0 -1 6 -2 8 3 C10 -2 16 -1 16 4 C16 9 8 14 8 14 Z'

function Shadow({ cy, rx, className }: { cy: number; rx: number; className?: string }) {
  // An animated shadow's keyframes set its opacity; the attribute is their first frame (14%), so the still pose
  // (reduced motion) keeps a soft shadow. A still one is 12%, as on the canvas.
  return <ellipse className={className} cx="80" cy={cy} rx={rx} ry="5" fill={VISOR} opacity={className ? 0.14 : 0.12} />
}

function Stem() {
  return <line x1="80" y1="42" x2="80" y2="22" stroke={BODY} strokeWidth="5" strokeLinecap="round" />
}

function Light({ fill = LIGHT, className }: { fill?: string; className?: string }) {
  return <circle className={className} cx="80" cy="19" r="7" fill={fill} />
}

/** Body, highlight and visor: the same in every variant. */
function Shell() {
  return (
    <>
      <rect x="24" y="40" width="112" height="106" rx="44" fill={BODY} />
      <ellipse cx="50" cy="60" rx="11" ry="6" fill="#FFFFFF" opacity="0.35" transform="rotate(-32 50 60)" />
      <rect x="44" y="68" width="72" height="40" rx="20" fill={VISOR} />
    </>
  )
}

function Cheeks({ rx = 7, ry = 4, fill = CHEEK }: { rx?: number; ry?: number; fill?: string }) {
  return (
    <>
      <ellipse cx="44" cy="122" rx={rx} ry={ry} fill={fill} />
      <ellipse cx="116" cy="122" rx={rx} ry={ry} fill={fill} />
    </>
  )
}

function RoundEyes({ cx = [67, 93], cy = 88, rx = 6, ry = 7, className = 'pb-blink' }: {
  cx?: [number, number]
  cy?: number
  rx?: number
  ry?: number
  className?: string
}) {
  return (
    <>
      <ellipse className={className} cx={cx[0]} cy={cy} rx={rx} ry={ry} fill={EYE} />
      <ellipse className={className} cx={cx[1]} cy={cy} rx={rx} ry={ry} fill={EYE} />
    </>
  )
}

const smile = <path d="M75 123 Q80 127 85 123" stroke={VISOR} strokeWidth="3" fill="none" strokeLinecap="round" />
const flatMouth = <path d="M76 124 L84 124" stroke={VISOR} strokeWidth="3" strokeLinecap="round" />
const openSmile = (
  <path d="M72 119 Q80 132 88 119 Z" fill={VISOR} stroke={VISOR} strokeWidth="2" strokeLinejoin="round" />
)
const grin = <path d="M73 121 Q80 129 87 121" stroke={VISOR} strokeWidth="3" fill="none" strokeLinecap="round" />
const ohMouth = <circle cx="80" cy="125" r="4" stroke={VISOR} strokeWidth="3" fill="none" />
const arcEyes = (
  <>
    <path d="M60 92 Q67 81 74 92" stroke={EYE} strokeWidth="4.5" fill="none" strokeLinecap="round" />
    <path d="M86 92 Q93 81 100 92" stroke={EYE} strokeWidth="4.5" fill="none" strokeLinecap="round" />
  </>
)
const wideEyes = (
  <>
    <circle cx="66" cy="88" r="9" fill={EYE} />
    <circle cx="94" cy="88" r="9" fill={EYE} />
    <circle cx="69" cy="85" r="3" fill="#FFFFFF" />
    <circle cx="97" cy="85" r="3" fill="#FFFFFF" />
  </>
)

function Heart({ x, y, scale, fill, className }: { x: number; y: number; scale?: number; fill: string; className: string }) {
  return (
    <g transform={`translate(${x} ${y})${scale ? ` scale(${scale})` : ''}`}>
      <path className={className} d={HEART_PATH} fill={fill} />
    </g>
  )
}

/** The drawing for each mood and variant, back to front, as on the canvas. The type makes all 16 required. */
const DRAWINGS: { [M in Mood]: Record<(typeof VARIANTS)[M][number], () => ReactNode> } = {
  idle: {
    float: () => (
      <>
        <Shadow cy={160} rx={46} className="pb-shadow" />
        <g className="pb-float-7">
          <g className="pb-wiggle">
            <Stem />
            <Light />
          </g>
          <Shell />
          <RoundEyes />
          {smile}
        </g>
      </>
    ),
    breathe: () => (
      <>
        <Shadow cy={148} rx={50} />
        <g className="pb-breathe">
          <Stem />
          <Light className="pb-glow" />
          <Shell />
          <RoundEyes className="pb-slowblink" />
          <Cheeks />
          {smile}
        </g>
      </>
    ),
    look: () => (
      <>
        <Shadow cy={148} rx={50} />
        <g className="pb-lean">
          <Stem />
          <Light />
          <Shell />
          <g className="pb-look">
            <RoundEyes />
          </g>
          {smile}
        </g>
      </>
    ),
    hop: () => (
      <>
        <Shadow cy={152} rx={50} className="pb-hopshadow" />
        <g transform="translate(0 6)">
          <g className="pb-hop">
            <Stem />
            <Light />
            <Shell />
            <RoundEyes />
            <Cheeks />
            {smile}
          </g>
        </g>
      </>
    ),
  },
  thinking: {
    scan: () => (
      <>
        <Shadow cy={160} rx={46} />
        <g className="bot-extra">
          <circle className="pb-p1" cx="132" cy="34" r="3.5" fill={LILAC} />
          <circle className="pb-p2" cx="142" cy="23" r="4.5" fill={LILAC} />
          <circle className="pb-p3" cx="152" cy="10" r="5.5" fill={LILAC} />
        </g>
        <g transform="rotate(-7 80 146)">
          <Stem />
          <Light className="pb-p1" />
          <Shell />
          <g className="pb-scan">
            <circle cx="71" cy="83" r="5.5" fill={EYE} />
            <circle cx="97" cy="83" r="5.5" fill={EYE} />
          </g>
          {flatMouth}
        </g>
      </>
    ),
    typing: () => (
      <>
        <Shadow cy={160} rx={46} />
        <g className="pb-float-5">
          <Stem />
          <Light />
          <Shell />
          <circle className="pb-t1" cx="65" cy="90" r="5" fill={EYE} />
          <circle className="pb-t2" cx="80" cy="90" r="5" fill={EYE} />
          <circle className="pb-t3" cx="95" cy="90" r="5" fill={EYE} />
          {flatMouth}
        </g>
      </>
    ),
    ponder: () => (
      <>
        <Shadow cy={150} rx={50} />
        <g className="pb-rock">
          <Stem />
          <Light className="pb-p1" />
          <Shell />
          <RoundEyes cx={[69, 95]} cy={82} rx={5.5} ry={6} />
          <path
            d="M73 124 Q76.5 120 80 124 Q83.5 128 87 124"
            stroke={VISOR}
            strokeWidth="3"
            fill="none"
            strokeLinecap="round"
          />
        </g>
      </>
    ),
    radar: () => (
      <>
        <Shadow cy={150} rx={50} />
        <g className="bot-extra">
          <circle className="pb-ping1" cx="80" cy="19" r="7" fill="none" stroke={LIGHT} strokeWidth="2.5" />
          <circle className="pb-ping2" cx="80" cy="19" r="7" fill="none" stroke={LIGHT} strokeWidth="2.5" />
        </g>
        <Stem />
        <Light />
        <Shell />
        <RoundEyes cx={[71, 97]} cy={81} rx={5.5} ry={6} />
        <circle cx="80" cy="125" r="3" fill={VISOR} />
      </>
    ),
  },
  happy: {
    bounce: () => (
      <>
        <Shadow cy={160} rx={46} />
        <g className="bot-extra">
          <path className="pb-p1" d="M134 40 l3 7 7 3 -7 3 -3 7 -3 -7 -7 -3 7 -3 z" fill={LIGHT} />
          <path className="pb-p3" d="M20 54 l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2 z" fill={LIGHT} />
        </g>
        <g className="pb-squish">
          <g className="pb-wiggle-fast">
            <Stem />
            <Light />
          </g>
          <Shell />
          {arcEyes}
          <Cheeks rx={8} ry={5} fill={BLUSH} />
          {openSmile}
        </g>
      </>
    ),
    spin: () => (
      <>
        <Shadow cy={160} rx={46} className="pb-spinshadow" />
        <g transform="translate(0 6)">
          <g className="pb-spinjump">
            <Stem />
            <Light />
            <Shell />
            {arcEyes}
            <Cheeks rx={8} ry={5} fill={BLUSH} />
            {openSmile}
          </g>
        </g>
      </>
    ),
    dance: () => (
      <>
        <Shadow cy={150} rx={50} />
        <g className="bot-extra" fontWeight="800" fontFamily="Nunito, sans-serif">
          <text className="pb-rise1" x="128" y="46" fontSize="24" fill={BODY}>
            ♪
          </text>
          <text className="pb-rise2" x="16" y="62" fontSize="22" fill={BLUSH}>
            ♫
          </text>
        </g>
        <g className="pb-dance">
          <g className="pb-wiggle-fast">
            <Stem />
            <Light />
          </g>
          <Shell />
          {arcEyes}
          <Cheeks rx={8} ry={5} fill={BLUSH} />
          {grin}
        </g>
      </>
    ),
    hearts: () => (
      <>
        <Shadow cy={160} rx={46} />
        <g className="bot-extra">
          <Heart x={124} y={34} scale={0.8} fill={HEART} className="pb-rise1" />
          <Heart x={18} y={50} scale={0.6} fill={BLUSH} className="pb-rise2" />
        </g>
        <g className="pb-float-6">
          <Stem />
          <Light fill={HEART} />
          <Shell />
          <Heart x={59} y={81} fill={HEART} className="pb-beat" />
          <Heart x={85} y={81} fill={HEART} className="pb-beat" />
          <Cheeks rx={9} ry={5.5} fill={BLUSH} />
          {grin}
        </g>
      </>
    ),
  },
  alert: {
    shake: () => (
      <>
        <Shadow cy={160} rx={42} />
        <g className="pb-shake">
          <path
            className="bot-extra"
            d="M48 24 L55 33 M34 38 L44 42 M112 24 L105 33 M126 38 L116 42"
            stroke={WARN}
            strokeWidth="4"
            strokeLinecap="round"
          />
          <g transform="translate(80 146) scale(0.94 1.06) translate(-80 -146)">
            <Stem />
            <Light fill={WARN} />
            <Shell />
            {wideEyes}
            {ohMouth}
          </g>
        </g>
      </>
    ),
    startle: () => (
      <>
        <Shadow cy={152} rx={50} className="pb-startleshadow" />
        <g transform="translate(0 4)">
          <g className="pb-startle">
            <Stem />
            <Light fill={WARN} />
            <Shell />
            <circle cx="66" cy="88" r="9" fill={EYE} />
            <circle cx="94" cy="88" r="9" fill={EYE} />
            <circle cx="66" cy="88" r="3.5" fill={VISOR} />
            <circle cx="94" cy="88" r="3.5" fill={VISOR} />
            <ellipse cx="80" cy="126" rx="4" ry="5" fill={VISOR} />
          </g>
        </g>
      </>
    ),
    siren: () => (
      <>
        <Shadow cy={150} rx={50} />
        <g className="bot-extra">
          <g className="pb-beam">
            <path d="M80 19 L66 -14 L94 -14 Z" fill={SIREN} opacity="0.3" />
            <path d="M80 19 L47 5 L47 33 Z" fill={LIGHT} opacity="0.3" />
            <path d="M80 19 L113 5 L113 33 Z" fill={LIGHT} opacity="0.3" />
          </g>
          {/* opacity: the halo's first frame, for the still pose */}
          <circle className="pb-halo" cx="80" cy="19" r="13" fill={SIREN} opacity="0.15" />
        </g>
        <Stem />
        <Light fill={SIREN} className="pb-siren" />
        <Shell />
        {wideEyes}
        <path d="M74 126 L86 126" stroke={VISOR} strokeWidth="3" strokeLinecap="round" />
      </>
    ),
    pop: () => (
      <>
        <Shadow cy={150} rx={50} />
        <g className="pb-pop bot-extra">
          <circle cx="130" cy="30" r="15" fill={SIREN} />
          <rect x="128" y="20" width="4.5" height="12" rx="2.25" fill="#FFFFFF" />
          <circle cx="130.25" cy="37.5" r="2.5" fill="#FFFFFF" />
        </g>
        <g className="pb-freeze">
          <Stem />
          <Light fill={WARN} />
          <Shell />
          <circle className="pb-widen" cx="66" cy="88" r="9" fill={EYE} />
          <circle className="pb-widen" cx="94" cy="88" r="9" fill={EYE} />
          {ohMouth}
        </g>
      </>
    ),
  },
}

export function Robot({ mood = 'idle', variant, size = 64, className = '' }: {
  mood?: Mood
  /** One of the mood's four animations; the mood's first (option A) when not given. */
  variant?: Variant
  size?: number
  className?: string
}) {
  const drawings: Record<string, () => ReactNode> = DRAWINGS[mood]
  const pick: Variant = variant && variant in drawings ? variant : VARIANTS[mood][0]
  const draw = drawings[pick]
  return (
    <svg
      className={`robot mood-${mood} ${className}`.trim()}
      data-mood={mood}
      data-variant={pick}
      width={size}
      height={(size * 170) / 160}
      viewBox="0 0 160 170"
      aria-hidden="true"
    >
      {draw()}
    </svg>
  )
}
