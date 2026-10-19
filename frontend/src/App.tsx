import { useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type JSX } from 'react'
import { roleOf, seesDev, seesUsage } from './access.ts'
import { examples as fetchExamples, health, type Example, type Health } from './api.ts'
import { AccessContext } from './auth/AccessGate.tsx'
import { ChatDivider } from './chat/ChatDivider.tsx'
import { ChatWindow } from './chat/ChatWindow.tsx'
import { PatchButton } from './chat/PatchButton.tsx'
import { useChat } from './chat/useChat.ts'
import { useChatLayout } from './chat/useChatLayout.ts'
import { usePatch } from './chat/usePatch.ts'
import { Brand } from './components/Brand.tsx'
import { BellIcon, ChatIcon, ChevronIcon, CodeIcon, DashboardIcon, InfoIcon, ListIcon, MoonIcon, SunIcon } from './components/Icons.tsx'
import { Robot } from './components/Robot.tsx'
import { ProfileContext, useProfileState } from './components/Profile.tsx'
import { UserMenu, type Account } from './components/UserMenu.tsx'
import { Landing } from './landing/Landing.tsx'
import { CvePage } from './pages/CvePage.tsx'
import { CvesPage } from './pages/CvesPage.tsx'
import { DashboardPage } from './pages/Dashboard.tsx'
import { DevPage } from './pages/DevPage.tsx'
import { SettingsPage } from './pages/SettingsPage.tsx'
import { NotFoundPage } from './pages/NotFoundPage.tsx'
import { PATHS, useRoute, type NavPage, type Page } from './route.ts'
import { store } from './storage.ts'
import { useTheme } from './theme.ts'
import { usePageContext } from './usePageContext.ts'

// The app shell (docs/design/DESIGN.md §4): a floating sidebar that collapses to an icon rail (a bottom tab bar on
// phones), a top bar with breadcrumb, page title and the light/dark toggle, then the page. Each page has a path
// (route.ts), so links and reloads land on the right page.
const PAGES: Record<Page, { title: string; nav: string; Icon: () => JSX.Element }> = {
  dashboard: { title: 'Dashboard', nav: 'Dashboard', Icon: DashboardIcon },
  cves: { title: 'CVEs', nav: 'CVEs', Icon: ListIcon },
  settings: { title: 'Settings', nav: 'Settings', Icon: BellIcon },
  dev: { title: 'Dev', nav: 'Dev', Icon: CodeIcon }, // one name everywhere (B50: the title said "Dev panel")
  about: { title: 'About', nav: 'About', Icon: InfoIcon }, // the landing page inside the app (B42)
  notFound: { title: 'Page not found', nav: '', Icon: InfoIcon }, // B49: any other address; no sidebar item
}

// Questions that fit the page under the chat (1–2, DESIGN.md §6.2). FakeLLM answers each one.
const SUGGESTIONS: Record<Page, string[]> = {
  dashboard: ['What should I fix first?', 'Explain CVE-2025-3248 and how to defend against it.'],
  cves: ['What should I fix first?', 'Explain CVE-2025-3248 and how to defend against it.'],
  settings: ['How do I protect a RAG app from indirect prompt injection?'],
  dev: ['What does an "ignore previous instructions" attack look like?'],
  about: ['What should I fix first?'],
  notFound: ['What should I fix first?'],
}

// `account`: the signed-in user, with sign-in on (B10, auth/ClerkApp.tsx): the top bar shows the user menu.
export default function App({ account }: { account?: Account } = {}) {
  const [status, setStatus] = useState<Health | null>(null)
  const access = useContext(AccessContext) // B45: the caller's role
  const [offline, setOffline] = useState(false)
  const [theme, toggleTheme] = useTheme()
  const [collapsed, setCollapsed] = useState(() => store.get('sidenavCollapsed') === '1')
  const [route, navigate] = useRoute()
  const page = route.page
  // Page context (A18): what Patch is told about the page; its rules live in pageContext.ts.
  const pageContext = usePageContext(route)
  // B49 C5: the conversation is kept for the tab's life per user (sign-in off: the one local user)
  const chat = useChat(pageContext.current, account ? (account.id ?? null) : 'local')
  const layout = useChatLayout()
  const chatOpen = layout.open
  const [examples, setExamples] = useState<Example[]>([])
  const patch = usePatch(chat, chatOpen) // one mood and one animation for the button and the chat header
  const patchButton = useRef<HTMLButtonElement>(null)
  const profile = useProfileState() // B48: the user menu and Settings' Profile card share it

  // After the Dev page saves a model choice, the snapshot card shows the new model.
  const refreshHealth = useCallback(() => {
    health().then(setStatus, () => setOffline(true))
  }, [])

  useEffect(() => {
    refreshHealth()
    fetchExamples().then(setExamples, () => setExamples([]))
  }, [refreshHealth])

  function openChat() {
    // A chat that opens focuses its message box itself; one already open gets the focus back here.
    if (layout.open) document.querySelector<HTMLTextAreaElement>('.chat-window textarea')?.focus()
    else layout.setOpen(true)
  }

  // "Ask about this" and a CVE page's "Ask Patch": open the chat where it is and ask about one CVE (DESIGN.md §6.4).
  function askAbout(cveId: string) {
    openChat()
    void chat.send(`Explain ${cveId} and how to defend against it.`, { savedLevel: true }) // A19: the saved level
  }

  // "Ask about this" on the CVEs page also selects the row: Patch knows which CVE "this" is (A18). While a reply is
  // still coming the chat takes no new question, so the click only opens the chat and selects nothing. On a CVE's own
  // page (B35) Patch is told that CVE already.
  function askAboutRow(cveId: string) {
    pageContext.select(cveId, chat.pending)
    askAbout(cveId)
  }

  function closeChat() {
    layout.setOpen(false)
    // Keyboard users land back on the button that opened it (it reappears once a pinned chat closes).
    setTimeout(() => patchButton.current?.focus())
  }

  // Ctrl/Cmd+K opens the chat on any page; Esc closes the bubble, never a pinned chat (DESIGN.md §6.4).
  // Bound on every render, so it always sees the current layout. A layout effect, so it's bound in the same task that
  // puts the shell on screen: a plain effect runs a moment later, and a Ctrl+K in that moment was lost (#67).
  useLayoutEffect(() => {
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

  // Dev only when the backend allows the dev panel (it exposes internals), and (B45) not for a Viewer. The role comes
  // from /access on each page load, so the owner's change shows on the next one.
  const devShown = seesDev(roleOf(access))
  const pages: NavPage[] = status?.dev_panel && devShown
    ? ['dashboard', 'cves', 'settings', 'dev'] : ['dashboard', 'cves', 'settings']
  const current = PAGES[page]
  const dark = theme === 'dark'

  return (
    <ProfileContext.Provider value={profile}>
    <div className={`app${collapsed ? ' collapsed' : ''}${layout.docked ? ' docked' : ''}`}>
      <aside className="sidenav" aria-label="Main">
        <Brand />
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
                onClick={() => navigate(PATHS[p])}
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
          {/* B42: the landing page, so it isn't lost after the first visit (and the only way to it with sign-in off) */}
          <span className="side-section">Patch</span>
          <button
            type="button"
            className="side-link"
            aria-current={page === 'about' ? 'page' : undefined}
            onClick={() => navigate(PATHS.about)}
            title={collapsed ? PAGES.about.nav : undefined}
          >
            <span className="side-icon">
              <InfoIcon />
            </span>
            <span className="side-label">{PAGES.about.nav}</span>
          </button>
        </nav>
        <div className="side-card">
          <Robot size={64} variant={patch.restVariant} />
          <strong>{status?.mode === 'live' ? 'Live data' : 'Snapshot'}</strong>
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
            {/* One CVE's page (B35) is under CVEs: its id is the title */}
            <h1>{route.cve ?? current.title}</h1>
          </div>
          {account && <UserMenu account={account} />}
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
            // keyed by the visit, like the CVEs page: a link followed again with another filter starts from it
            <DashboardPage
              key={route.visit}
              search={route.search}
              onNavigate={navigate}
              onAskPatch={openChat}
              onView={pageContext.reportView}
              patchVariant={patch.restVariant}
            />
          ) : page === 'cves' && route.cve ? (
            // keyed by the visit: Back and forward between two CVEs' pages start each from its own data
            <CvePage
              key={route.visit}
              id={route.cve}
              asOf={status?.as_of ?? null}
              onAsk={askAboutRow}
              onNavigate={navigate}
            />
          ) : page === 'cves' ? (
            // keyed by the visit: a link followed again with other filters starts from them
            <CvesPage
              key={route.visit}
              search={route.search}
              onAsk={askAboutRow}
              selected={pageContext.selected}
              onView={pageContext.reportView}
            />
          ) : page === 'notFound' ? (
            // B49 (#96 O1): an address the app has no page for. Keyed by the visit: another bad address starts fresh
            <NotFoundPage
              key={route.visit}
              path={window.location.pathname}
              variant={patch.restVariant}
              onNavigate={navigate}
            />
          ) : page === 'about' ? (
            <Landing place="about" onNavigate={navigate} />
          ) : page === 'settings' ? (
            <SettingsPage asOf={status?.as_of ?? null} mode={status?.mode} onServerSaved={refreshHealth} />
          ) : status?.dev_panel && devShown ? (
            <DevPage onSaved={refreshHealth} />
          ) : status?.dev_panel ? (
            // B45: a Viewer who types /dev: one line, no internals (the server refuses its routes too)
            <div className="page">
              <p className="muted" data-testid="dev-not-yours">
                The Dev page is for people the owner trusts with Patch's internals. Ask the owner if you need it.
              </p>
            </div>
          ) : null}
        </main>
      </div>

      {/* Same places in the tree in every layout: pinning or unpinning never rebuilds the page or the chat. */}
      {layout.docked && <ChatDivider layout={layout} />}
      {chatOpen && (
        <ChatWindow
          chat={chat}
          mood={patch.mood}
          variant={patch.variant}
          restVariant={patch.restVariant}
          pageTitle={current.title}
          words={pageContext.words}
          suggestions={SUGGESTIONS[page]}
          examples={examples}
          layout={layout}
          asOf={status?.as_of ?? null}
          onClose={closeChat}
          showUsage={seesUsage(roleOf(access))}
        />
      )}
      {/* Hidden while the chat is pinned beside the page (DESIGN.md §6.3). */}
      {!layout.docked && (
        <PatchButton
          ref={patchButton}
          open={chatOpen}
          mood={patch.mood}
          variant={patch.variant}
          unread={patch.unread}
          onClick={() => (chatOpen ? layout.setOpen(false) : openChat())}
        />
      )}
    </div>
    </ProfileContext.Provider>
  )
}
