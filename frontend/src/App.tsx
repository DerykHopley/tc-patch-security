import { useEffect, useState, type JSX } from 'react'
import { health, type Health } from './api.ts'
import { BellIcon, ChatIcon, ChevronIcon, CodeIcon, DashboardIcon, MoonIcon, ShieldIcon, SunIcon } from './components/Icons.tsx'
import { Robot } from './components/Robot.tsx'
import { DashboardPage } from './pages/Dashboard.tsx'
import { EmptyPage } from './pages/EmptyPage.tsx'
import { store } from './storage.ts'
import { useTheme } from './theme.ts'

// The app shell (docs/design/DESIGN.md §4): a floating sidebar that collapses to an icon rail (a bottom tab bar on
// phones), a top bar with breadcrumb, page title and the light/dark toggle, then the page.
type Page = 'dashboard' | 'settings' | 'dev'

const PAGES: Record<Page, { title: string; nav: string; Icon: () => JSX.Element; comingWith: string }> = {
  dashboard: { title: 'Dashboard', nav: 'Dashboard', Icon: DashboardIcon, comingWith: 'the CVE dashboard tickets' },
  settings: { title: 'Settings', nav: 'Settings', Icon: BellIcon, comingWith: 'the settings and alerts ticket' },
  dev: { title: 'Dev panel', nav: 'Dev', Icon: CodeIcon, comingWith: 'the dev panel ticket' },
}

export default function App() {
  const [status, setStatus] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)
  const [theme, toggleTheme] = useTheme()
  const [collapsed, setCollapsed] = useState(() => store.get('sidenavCollapsed') === '1')
  const [page, setPage] = useState<Page>('dashboard')

  useEffect(() => {
    health().then(setStatus, () => setOffline(true))
  }, [])

  function toggleCollapsed() {
    const next = !collapsed
    store.set('sidenavCollapsed', next ? '1' : '0')
    setCollapsed(next)
  }

  // Dev only when the backend allows the dev panel (it exposes internals).
  const pages: Page[] = status?.dev_panel ? ['dashboard', 'settings', 'dev'] : ['dashboard', 'settings']
  const current = PAGES[page]
  const dark = theme === 'dark'

  return (
    <div className={`app${collapsed ? ' collapsed' : ''}`}>
      <aside className="sidenav" aria-label="Main">
        <div className="brand">
          <span className="brand-mark">
            <ShieldIcon />
          </span>
          <span className="brand-name">
            <span>LLM Security</span>
            <small>assistant</small>
          </span>
        </div>
        <nav className="side-links" aria-label="Pages">
          <span className="side-section">Monitor</span>
          {pages.map((p) => {
            const { nav, Icon } = PAGES[p]
            return (
              <button
                key={p}
                type="button"
                className="side-link"
                aria-current={page === p ? 'page' : undefined}
                onClick={() => setPage(p)}
                title={collapsed ? nav : undefined}
              >
                <span className="side-icon">
                  <Icon />
                </span>
                <span className="side-label">{nav}</span>
              </button>
            )
          })}
          <span className="side-section">Assistant</span>
          {/* A placeholder until the chat ticket (A06): reachable and named, but it does nothing yet. */}
          <button
            type="button"
            className="side-link side-ask"
            aria-label="Ask Patch"
            aria-disabled="true"
            aria-describedby="ask-soon"
            title="Ask Patch: the chat is coming soon"
          >
            <span className="side-icon">
              <ChatIcon />
            </span>
            <span className="side-label">
              Ask<span className="long"> Patch</span>
            </span>
            <span id="ask-soon" className="visually-hidden">
              Coming soon
            </span>
          </button>
        </nav>
        <div className="side-card">
          <Robot size={64} />
          <strong>Snapshot</strong>
          <span>{status ? `Data as of ${status.as_of}` : offline ? 'Backend offline' : 'Loading…'}</span>
          <span className="side-model">{status?.model ?? '—'}</span>
        </div>
        <button
          type="button"
          className="collapse-btn"
          onClick={toggleCollapsed}
          aria-label={collapsed ? 'Expand the sidebar' : 'Collapse the sidebar'}
          title={collapsed ? 'Expand' : 'Collapse'}
        >
          <ChevronIcon />
        </button>
      </aside>

      <div className="main-col">
        <header className="topbar">
          <div className="crumbs">
            <span className="crumb-path">Pages / {current.title}</span>
            <h1>{current.title}</h1>
          </div>
          <button
            type="button"
            className="theme-btn"
            onClick={toggleTheme}
            aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            title={dark ? 'Light mode' : 'Dark mode'}
          >
            {dark ? <SunIcon /> : <MoonIcon />}
          </button>
        </header>
        <main>
          {page === 'dashboard' ? (
            <DashboardPage />
          ) : (
            <EmptyPage title={current.title} comingWith={current.comingWith} />
          )}
        </main>
      </div>
    </div>
  )
}
