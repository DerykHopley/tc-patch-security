import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'
import { REQUEST_ACCESS_PATH, SIGN_IN_PATH } from '../auth/signInView.ts'
import { Brand } from '../components/Brand.tsx'
import { MoonIcon, SunIcon } from '../components/Icons.tsx'
import { Robot } from '../components/Robot.tsx'
import { pickPose } from '../components/patchPose.ts'
import { followLink, openPath } from '../route.ts'
import { useTheme, type Theme } from '../theme.ts'
import '../styles/landing.css'
import chatDark from './shots/chat-dark.webp'
import chatLight from './shots/chat-light.webp'
import cvesDark from './shots/cves-dark.webp'
import cvesLight from './shots/cves-light.webp'
import dashboardDark from './shots/dashboard-dark.webp'
import dashboardLight from './shots/dashboard-light.webp'

// The landing page (B42, #80; DESIGN.md §5.16). Two places, one page:
// - the front door: what a signed-out visitor sees with sign-in on, at any address but the sign-in form's
//   (auth/signInView.ts `frontDoor`). Its own top bar (the brand, the theme switch); its next step is Sign in or
//   Request access.
// - About (`/about`), inside the app shell for anyone signed in, and with sign-in off: the same page, its next step
//   the dashboard.
// Fixed text and fixed example screenshots only: no API call, no live data, nobody's watchlist (the page shows
// before sign-in). The screenshots are taken by scripts/landing-shots.sh, light and dark; the page shows the pair
// that matches the theme.

const END_LINE: Record<Props['place'], string> = {
  'front-door': 'Sign in, or ask the owner for access.',
  access: 'The owner decides who gets in.',
  about: 'Your watchlist is on the dashboard.',
}

type Shot = 'dashboard' | 'cves' | 'chat'

const SHOTS: Record<Shot, Record<Theme, string>> = {
  dashboard: { light: dashboardLight, dark: dashboardDark },
  cves: { light: cvesLight, dark: cvesDark },
  chat: { light: chatLight, dark: chatDark },
}

const SHOWCASE: { shot: Shot; title: string; text: string; alt: string }[] = [
  {
    shot: 'dashboard',
    title: 'Everything open, at a glance',
    text: 'Tiles for the open, critical and actively exploited flaws, charts by product and severity, and the five to fix first.',
    alt: "Patch's dashboard: tiles for open, critical and exploited CVEs, a chart of open CVEs by product and "
      + 'severity, and the watchlist filter.',
  },
  {
    shot: 'cves',
    title: 'Every flaw, judged for your setup',
    text: 'Your version against the affected versions gives a verdict. Your policy gives a priority and a due date. '
      + 'Each decision is kept, with its reason.',
    alt: 'The CVEs page: each CVE on the watchlist with its priority, due date, severity, EPSS score and verdict, '
      + 'most urgent first.',
  },
  {
    shot: 'chat',
    title: 'Ask Patch, check the sources',
    text: "Patch looks it up in OWASP's lists, MITRE ATLAS and the CVE data, then answers with numbered sources you "
      + 'can open.',
    alt: 'Patch answering "Am I affected by CVE-2025-3248?" beside that CVE\'s page: affected, because 1.2.0 is '
      + 'before the fixed version 1.3.0, with the cited source open under the answer.',
  },
]

const TILES: { name: string; text: string; tone: string }[] = [
  { name: 'Watch', text: 'The LLM software you run, checked against NVD, CISA KEV, EPSS and OSV.dev.', tone: 'open' },
  { name: 'Judge', text: 'Affected or not, for your version. A priority and a due date by rules you set.', tone: 'critical' },
  { name: 'Alert', text: 'Newly exploited flaws, flagged once per CVE.', tone: 'kev' },
  { name: 'Ask', text: 'Questions about a risk, an attack or a CVE, answered with sources.', tone: 'new' },
]

// `access` (B46, #81): signed in but not approved (asked, waiting, refused, removed), at /about: the front door's
// frame and page, its next step back to their request (`/`, the access card). Nothing of the app.
type Props = { place: 'front-door' | 'access' } | { place: 'about'; onNavigate: (href: string) => void }

export function Landing(props: Props) {
  const theme = usePageTheme()
  const [pose] = useState(() => pickPose('idle', Math.random)) // no mood here: idle, picked once (DESIGN.md §8.3)
  const [endPose] = useState(() => pickPose('happy', Math.random))
  const front = props.place !== 'about' // its own page and top bar
  const signedOut = props.place === 'front-door'
  const Title = front ? 'h1' : 'h2' // in the app the top bar's "About" is the page's h1
  const go = (e: MouseEvent<HTMLAnchorElement>) => followLink(e, front ? openPath : props.onNavigate)

  const next = signedOut ? (
    <>
      <a className="pill-link primary" href={SIGN_IN_PATH} onClick={go}>Sign in</a>
      <a className="pill-link" href={REQUEST_ACCESS_PATH} onClick={go}>Request access</a>
    </>
  ) : props.place === 'access' ? (
    <a className="pill-link primary" href="/" onClick={go}>Back to your request</a>
  ) : (
    <a className="pill-link primary" href="/" onClick={go}>Open the dashboard</a>
  )

  return (
    <Frame front={front}>
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero-text">
          <p className="landing-kicker">For teams who run LLM software</p>
          <Title id="landing-title">Security flaws in your LLM stack, tracked for you</Title>
          <p className="landing-problem">
            LangChain, Ollama, Langflow, LiteLLM: the software behind your LLM apps gets new CVEs every week. Finding
            the ones that hit your versions means reading NVD, CISA's list of exploited flaws and each project's
            advisories, again and again.
          </p>
          <p className="landing-what">
            <strong>Patch</strong> does that reading for you. It watches the products you run, says which flaws
            affect you and what to fix first, and answers your questions with sources.
          </p>
          <div className="landing-next">{next}</div>
          {signedOut && (
            <p className="landing-note">New here? Request access: make an account, then the owner lets you in.</p>
          )}
        </div>
        <div className="landing-art">
          <Robot size={150} variant={pose.variant} />
          <div className="landing-alert">
            <span className="landing-alert-app">
              <span className="visually-hidden">An example alert on your phone: </span>Patch · now
            </span>
            <strong>Added to CISA KEV: CVE-2025-3248</strong>
            <span>Your Langflow 1.2.0 is affected. Urgent.</span>
          </div>
        </div>
      </section>

      <section className="landing-tiles" aria-labelledby="landing-tiles-title">
        <h2 id="landing-tiles-title" className="visually-hidden">What Patch does</h2>
        {TILES.map((t) => (
          <div key={t.name} className={`landing-tile landing-tile-${t.tone}`}>
            <h3>{t.name}</h3>
            <p>{t.text}</p>
          </div>
        ))}
      </section>

      <section className="landing-showcase" aria-labelledby="landing-showcase-title">
        <h2 id="landing-showcase-title">See it working</h2>
        {SHOWCASE.map((s) => (
          <figure key={s.shot} className="landing-shot">
            <div className="shot-frame">
              <span className="shot-dots" aria-hidden="true"><i /><i /><i /></span>
              <img src={SHOTS[s.shot][theme]} alt={s.alt} width={1280} height={800} loading="lazy" decoding="async" />
            </div>
            <figcaption>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </figcaption>
          </figure>
        ))}
        <p className="landing-small">
          Screenshots from Patch with example data: a made-up watchlist on public CVE data as of 2026-10-13, and a
          scripted test model in the chat.
        </p>
      </section>

      <section className="landing-end" aria-labelledby="landing-end-title">
        <Robot size={96} variant={endPose.variant} />
        <h2 id="landing-end-title">{signedOut ? 'Ready to look at your own stack?' : "That's Patch."}</h2>
        <p>{END_LINE[props.place]}</p>
        <div className="landing-next">{next}</div>
      </section>

      <footer className="landing-foot">
        <p>
          Data: NVD, CISA KEV, EPSS by FIRST, OSV.dev, the OWASP Top 10 lists and MITRE ATLAS. A Turing College
          project. <a href="https://github.com/DerykHopley/tc-patch-security" target="_blank" rel="noreferrer">Source
          on GitHub</a>
        </p>
      </footer>
    </Frame>
  )
}

/** The front door has its own page and top bar (the brand, the theme switch); About sits in the app's main column. */
function Frame({ front, children }: { front: boolean; children: ReactNode }) {
  if (!front) return <div className="landing landing-in-app">{children}</div>
  return (
    <div className="landing-page">
      <header className="landing-top">
        <Brand />
        <ThemeSwitch />
      </header>
      <main className="landing">{children}</main>
    </div>
  )
}

function ThemeSwitch() {
  const [theme, toggleTheme] = useTheme()
  const dark = theme === 'dark'
  return (
    <button
      type="button"
      className="theme-btn"
      onClick={toggleTheme}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={dark ? 'Light mode' : 'Dark mode'}
    >
      {dark ? <SunIcon /> : <MoonIcon />}
    </button>
  )
}

/** The page's theme, following `data-theme` on <html> (whoever switches it: this page's switch or the app's). */
function usePageTheme(): Theme {
  const [theme, setTheme] = useState(pageTheme)
  useEffect(() => {
    const watch = new MutationObserver(() => setTheme(pageTheme()))
    watch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => watch.disconnect()
  }, [])
  return theme
}

const pageTheme = (): Theme => (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')
