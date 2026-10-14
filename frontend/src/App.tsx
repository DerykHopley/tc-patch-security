import { useEffect, useRef, useState, type JSX } from 'react'
import { examples as fetchExamples, health, type Example, type Health } from './api.ts'
import { AlertBanner, useAlertLink } from './chat/AlertBanner.tsx'
import { ChatDivider } from './chat/ChatDivider.tsx'
import { ChatWindow } from './chat/ChatWindow.tsx'
import { PatchButton } from './chat/PatchButton.tsx'
import { useChat } from './chat/useChat.ts'
import { useChatLayout } from './chat/useChatLayout.ts'
import { usePatch } from './chat/usePatch.ts'
import { BellIcon, ChatIcon, ChevronIcon, CodeIcon, DashboardIcon, MoonIcon, ShieldIcon, SunIcon } from './components/Icons.tsx'
import { Robot } from './components/Robot.tsx'
import { DashboardPage } from './pages/Dashboard.tsx'
import { EmptyPage } from './pages/EmptyPage.tsx'
import { SettingsPage } from './pages/SettingsPage.tsx'
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
  const layout = useChatLayout()
  const [alertCve, alertDone] = useAlertLink()
  const chatOpen = layout.open
  const [examples, setExamples] = useState<Example[]>([])
  const patch = usePatch(chat, chatOpen) // one mood for the button and the chat header
  const patchButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    health().then(setStatus, () => setOffline(true))
    fetchExamples().then(setExamples, () => setExamples([]))
  }, [])

  function openChat() {
    layout.setOpen(true)
    // A chat that opens focuses its message box itself; one already open gets the focus back here.
    setTimeout(() => document.querySelector<HTMLTextAreaElement>('.chat-window textarea')?.focus())
  }

  // "Ask about this" and an alert's "Explain it": open the chat where it is and ask about one CVE (DESIGN.md §6.4).
  function askAbout(cveId: string) {
    openChat()
    void chat.send(`Explain ${cveId} and how to defend against it.`)
  }

  function closeChat() {
    layout.setOpen(false)
    // Keyboard users land back on the button that opened it (it reappears once a pinned chat closes).
    setTimeout(() => patchButton.current?.focus())
  }

  // Ctrl/Cmd+K opens the chat on any page; Esc closes the bubble, never a pinned chat (DESIGN.md §6.4).
  // Bound on every render, so it always sees the current layout.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault() // Firefox and Chrome would focus their own search box
        openChat()
      } else if (e.key === 'Escape' && layout.open && !layout.pinned) {
        closeChat()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

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
    <div className={`app${collapsed ? ' collapsed' : ''}${layout.docked ? ' docked' : ''}`}>
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
            onClick={() => (chatOpen ? closeChat() : openChat())}
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
        {alertCve && (
          <AlertBanner
            cve={alertCve}
            onExplain={() => {
              alertDone()
              askAbout(alertCve)
            }}
            onDismiss={alertDone}
          />
        )}
        <main>
          {page === 'dashboard' ? (
            <DashboardPage onAsk={askAbout} />
          ) : page === 'settings' ? (
            <SettingsPage asOf={status?.as_of ?? null} onOpenDashboard={() => setPage('dashboard')} />
          ) : (
            <EmptyPage title={current.title} comingWith={current.comingWith} />
          )}
        </main>
      </div>

      {/* Same places in the tree in every layout: pinning or unpinning never rebuilds the page or the chat. */}
      {layout.docked && <ChatDivider layout={layout} />}
      {chatOpen && (
        <ChatWindow
          chat={chat}
          mood={patch.mood}
          pageTitle={current.title}
          suggestions={SUGGESTIONS[page]}
          examples={examples}
          layout={layout}
          onClose={closeChat}
        />
      )}
      {/* Hidden while the chat is pinned beside the page (DESIGN.md §6.3). */}
      {!layout.docked && (
        <PatchButton
          ref={patchButton}
          open={chatOpen}
          mood={patch.mood}
          unread={patch.unread}
          onClick={() => (chatOpen ? layout.setOpen(false) : openChat())}
        />
      )}
    </div>
  )
}
