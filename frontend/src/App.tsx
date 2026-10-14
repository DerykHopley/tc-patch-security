import { useEffect, useRef, useState, type JSX } from 'react'
import { examples as fetchExamples, health, type Example, type Health } from './api.ts'
import { ChatWindow } from './chat/ChatWindow.tsx'
import { PatchButton } from './chat/PatchButton.tsx'
import { useChat } from './chat/useChat.ts'
import { usePatch } from './chat/usePatch.ts'
import { BellIcon, ChatIcon, ChevronIcon, CodeIcon, DashboardIcon, MoonIcon, ShieldIcon, SunIcon } from './components/Icons.tsx'
import { Robot } from './components/Robot.tsx'
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

// Questions that fit the page under the chat (1–2, DESIGN.md §6.2). FakeLLM answers each one.
const SUGGESTIONS: Record<Page, string[]> = {
  dashboard: [
    'Explain CVE-2025-3248 and how to defend against it.',
    'Which critical Langflow vulnerabilities were published in 2026?',
  ],
  settings: ['How do I protect a RAG app from indirect prompt injection?'],
  dev: ['What does an "ignore previous instructions" attack look like?'],
}

export default function App() {
  const [status, setStatus] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)
  const [theme, toggleTheme] = useTheme()
  const [collapsed, setCollapsed] = useState(() => store.get('sidenavCollapsed') === '1')
  const [page, setPage] = useState<Page>('dashboard')
  const chat = useChat()
  const [chatOpen, setChatOpen] = useState(false)
  const [examples, setExamples] = useState<Example[]>([])
  const patch = usePatch(chat, chatOpen) // one mood for the button and the chat header
  const patchButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    health().then(setStatus, () => setOffline(true))
    fetchExamples().then(setExamples, () => setExamples([]))
  }, [])

  function closeChat() {
    setChatOpen(false)
    patchButton.current?.focus() // keyboard users land back on the button that opened it
  }

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
          <button
            type="button"
            className="side-link side-ask"
            aria-label="Ask Patch"
            aria-expanded={chatOpen}
            aria-describedby={patch.unread ? 'patch-unread' : undefined}
            onClick={() => (chatOpen ? closeChat() : setChatOpen(true))}
            title={collapsed ? 'Ask Patch' : undefined}
          >
            <span className="side-icon">
              <ChatIcon />
            </span>
            <span className="side-label">
              Ask<span className="long"> Patch</span>
            </span>
            {patch.unread && <span className="unread-dot" aria-hidden="true" />}
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
          <EmptyPage title={current.title} comingWith={current.comingWith} />
        </main>
      </div>

      {chatOpen && (
        <ChatWindow
          chat={chat}
          mood={patch.mood}
          pageTitle={current.title}
          suggestions={SUGGESTIONS[page]}
          examples={examples}
          onClose={closeChat}
        />
      )}
      <PatchButton
        ref={patchButton}
        open={chatOpen}
        mood={patch.mood}
        unread={patch.unread}
        onClick={() => (chatOpen ? setChatOpen(false) : setChatOpen(true))}
      />
    </div>
  )
}
