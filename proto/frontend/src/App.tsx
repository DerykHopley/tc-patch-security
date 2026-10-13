import { useCallback, useEffect, useRef, useState } from "react";
import { examples as fetchExamples, health, type Example, type Health } from "./api";
import { ChatSurface } from "./components/ChatSurface";
import { Dashboard } from "./components/Dashboard";
import { DevPanel } from "./components/DevPanel";
import { Robot } from "./components/Robot";
import { BellIcon, ChatIcon, ChevronIcon, CodeIcon, DashboardIcon, MoonIcon, ShieldIcon, SunIcon } from "./components/Icons";
import { Settings } from "./components/Settings";
import { useChat } from "./hooks/useChat";
import { useMood } from "./hooks/useMood";

// The chat layout: a bubble. Patch's button opens a chat window over the page; enlarged, it can be pinned
// beside the page with a draggable divider. (Tabs, drawer and side panel were tried and removed.)
type Page = "dashboard" | "settings" | "dev";
// The design is Playful (set on <html> in index.html, fonts loaded there). Classic, Glass, Neon HUD and Clean sidebar
// were tried and removed or merged; see docs/design-examples. Light or dark is the one switch left.
type Theme = "light" | "dark";
const PAGE_ICON: Record<Page, () => React.JSX.Element> = { dashboard: DashboardIcon, settings: BellIcon, dev: CodeIcon };

const PAGE_LABEL: Record<Page, string> = { dashboard: "Dashboard", settings: "Settings", dev: "Dev panel" };

// Questions that fit the page under the chat. FakeLLM answers the CVE one from its script path.
const SUGGESTIONS: Record<Page, string[]> = {
  dashboard: ["Explain CVE-2025-3248 and how to defend against it.", "Which critical Langflow vulnerabilities were published in 2026?"],
  settings: ["How do I protect a RAG app from indirect prompt injection?"],
  dev: ["What does an \"ignore previous instructions\" attack look like?"],
};

// Per-browser conveniences: may be blocked (private windows), so never required.
const store = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
};

// Old `?layout=` links: split pins the chat; the others (tabs, drawer, panel, bubble) open the plain bubble.
const fromUrl = new URLSearchParams(window.location.search).get("layout");

// Light or dark: `?theme=` or the remembered choice, else the system setting.
function initialTheme(): Theme {
  const value = new URLSearchParams(window.location.search).get("theme") ?? store.get("theme");
  if (value === "light" || value === "dark") return value;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function initialPinned(): boolean {
  if (fromUrl) return fromUrl === "split";
  return store.get("pinned") === "1";
}

export default function App() {
  const chat = useChat();
  const [examples, setExamples] = useState<Example[]>([]);
  const [status, setStatus] = useState<Health | null>(null);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const mood = useMood(chat);
  const [collapsed, setCollapsed] = useState(() => store.get("sidenavCollapsed") === "1");
  const [pinned, setPinnedState] = useState(initialPinned);
  const [page, setPage] = useState<Page>("dashboard");
  const [chatOpen, setChatOpen] = useState(() => initialPinned()); // a pinned chat starts open
  const [expanded, setExpanded] = useState(false);
  const [helloHidden, setHelloHidden] = useState(() => store.get("helloHidden") === "1");
  const [splitWidth, setSplitWidth] = useState(() => Number(store.get("splitWidth")) || 440);
  const [alertHandled, setAlertHandled] = useState(false);
  const [alertCve] = useState(() => /^#cve=(CVE-\d{4}-\d{4,})$/i.exec(window.location.hash)?.[1]?.toUpperCase() ?? null);

  const docked = pinned && chatOpen;

  useEffect(() => {
    fetchExamples().then(setExamples).catch(() => setExamples([]));
    health().then(setStatus).catch(() => setStatus(null));
  }, [page]); // re-read on navigation, so the header shows the model just picked in the dev panel


  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);

  function toggleTheme() {
    setTheme((t) => { const next = t === "dark" ? "light" : "dark"; store.set("theme", next); return next; });
  }


  function toggleCollapsed() {
    setCollapsed((c) => { store.set("sidenavCollapsed", c ? "0" : "1"); return !c; });
  }

  // Pin (offered on the enlarged bubble) docks the chat beside the page; unpin floats it back, still enlarged.
  // Both keep the chat open with its conversation.
  function setPinned(p: boolean) {
    setPinnedState(p);
    store.set("pinned", p ? "1" : "0");
    if (!p) setExpanded(true);
    setChatOpen(true);
  }

  const openChat = useCallback(() => { setChatOpen(true); chat.markRead(); }, [chat]);

  // Ctrl/Cmd+K opens the chat over any page; Esc closes the bubble (a pinned chat stays).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openChat();
      } else if (e.key === "Escape" && chatOpen && !docked) {
        setChatOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [chatOpen, docked, openChat]);

  // U10: "Ask about this" opens the chat over the page and sends the question.
  function ask(question: string) {
    openChat();
    chat.send(question);
  }

  const go = setPage;

  // Pinned panel: drag the divider. Width kept between 320 px and 60% of the window.
  const dragging = useRef(false);
  useEffect(() => {
    function move(e: PointerEvent) {
      if (!dragging.current) return;
      const w = Math.min(Math.max(window.innerWidth - e.clientX, 320), window.innerWidth * 0.6);
      setSplitWidth(Math.round(w));
    }
    function up() {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.classList.remove("resizing");
      setSplitWidth((w) => { store.set("splitWidth", String(w)); return w; });
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
  }, []);

  // Patch says hello above the dashboard, until it's closed (remembered per browser).
  function hideHello() {
    setHelloHidden(true);
    store.set("helloHidden", "1");
  }

  const hello = !helloHidden && (
    <div className="bot-hero">
      <button type="button" className="icon-btn hero-close" onClick={hideHello} aria-label="Close Patch's welcome" title="Close">✕</button>
      <Robot size={110} className="wave" />
      <div>
        <p className="bot-hero-title">Hi there! I'm Patch, your security sidekick.</p>
        <p className="bot-hero-text">I watch the CVEs in your LLM stack and can explain any of them. Click "Ask about this" on a row, or just ask me.</p>
        <button type="submit" onClick={openChat}>Ask Patch</button>
      </div>
    </div>
  );

  const pageEl = (p: Page) =>
    p === "dashboard" ? <>{hello}<Dashboard onAsk={ask} /></>
      : p === "settings" ? <Settings asOf={status?.as_of ?? null} onOpenDashboard={() => go("dashboard")} />
      : <DevPanel />;

  const surface = (opts: { onClose?: () => void; onExpand?: () => void; onPin?: () => void; pinned?: boolean }) => (
    <ChatSurface chat={chat} examples={examples} pageLabel={PAGE_LABEL[page]} suggestions={SUGGESTIONS[page]}
      autoFocus={chatOpen} expanded={expanded} {...opts} />
  );

  const pages: Page[] = status?.dev_panel ? ["dashboard", "settings", "dev"] : ["dashboard", "settings"];
  const unread = !chatOpen && chat.unread && chat.messages.length > 0;
  const toggleChat = () => (chatOpen ? setChatOpen(false) : openChat());


  const themeBtn = (
    <button type="button" className="theme-btn" onClick={toggleTheme} aria-pressed={theme === "dark"}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"} title={theme === "dark" ? "Light mode" : "Dark mode"}>
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );

  return (
    <div className={`app design-playful has-sidenav${collapsed ? " collapsed" : ""}`}>
      <aside className="sidenav" aria-label="Main">
        <div className="brand">
          <span className="brand-mark"><ShieldIcon /></span>
          <span className="brand-name">LLM Security<small>assistant · prototype</small></span>
        </div>
        <nav className="side-links" aria-label="Pages">
          <span className="side-section">Monitor</span>
          {pages.map((p) => {
            const Icon = PAGE_ICON[p];
            return (
              <button key={p} type="button" className="side-link" aria-pressed={page === p} onClick={() => go(p)} title={PAGE_LABEL[p]}>
                <span className="side-icon"><Icon /></span>
                <span className="side-label">{p === "dev" ? "Dev" : PAGE_LABEL[p]}</span>
              </button>
            );
          })}
          <span className="side-section">Assistant</span>
          <button type="button" className="side-link side-ask" aria-expanded={chatOpen} onClick={toggleChat} title="Ask Patch (Ctrl K)">
            <span className="side-icon"><ChatIcon /></span>
            <span className="side-label">{chatOpen ? "Hide chat" : <>Ask<span className="long"> Patch</span></>}</span>
            {unread && <span className="unread-dot" aria-label="New answer" />}
          </button>
        </nav>
        <div className="side-card">
          <Robot size={64} className="side-bot" />
          <strong>Snapshot</strong>
          <span>{status ? `Data as of ${status.as_of}` : "Backend offline"}</span>
          <span className="side-model">{status?.model ?? "—"}</span>
        </div>
        <button type="button" className="collapse-btn" onClick={toggleCollapsed} aria-pressed={collapsed}
          aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"} title={collapsed ? "Expand" : "Collapse"}>
          <ChevronIcon />
        </button>
      </aside>

      <div className="main-col">
        <header className="topbar">
          <div className="crumbs">
            <span className="crumb-path">Pages / {PAGE_LABEL[page]}</span>
            <h1>{PAGE_LABEL[page]}</h1>
          </div>
          {themeBtn}
        </header>

      {alertCve && !alertHandled && (
        <div className="alert-banner" role="status">
          You opened an alert for <strong>{alertCve}</strong>.
          <button type="submit" onClick={() => { setAlertHandled(true); history.replaceState(null, "", " "); ask(`Explain ${alertCve} and how to defend against it.`); }}>
            Explain it
          </button>
          <button type="button" onClick={() => { setAlertHandled(true); history.replaceState(null, "", " "); }}>Dismiss</button>
        </div>
      )}

      {/* One stage, so the page isn't rebuilt when the chat is pinned or unpinned. */}
      <div className={`stage${docked ? " split" : ""}`} style={docked ? { gridTemplateColumns: `minmax(0, 1fr) 6px ${splitWidth}px` } : undefined}>
        <main className="dash-page">{pageEl(page)}</main>
        {docked ? (
          <>
            <div className="divider" role="separator" aria-orientation="vertical" aria-label="Resize the chat" tabIndex={0}
              onPointerDown={() => { dragging.current = true; document.body.classList.add("resizing"); }}
              onKeyDown={(e) => {
                if (e.key === "ArrowLeft") setSplitWidth((w) => Math.min(w + 24, window.innerWidth * 0.6));
                if (e.key === "ArrowRight") setSplitWidth((w) => Math.max(w - 24, 320));
              }} />
            <aside className="split-chat" aria-label="Chat">
              {surface({ onClose: () => setChatOpen(false), onPin: () => setPinned(false), pinned: true })}
            </aside>
          </>
        ) : chatOpen && (
          <aside className={`bubble-window${expanded ? " expanded" : ""}`} aria-label="Chat">
            {surface({ onClose: () => setChatOpen(false), onExpand: () => setExpanded((x) => !x), onPin: expanded ? () => setPinned(true) : undefined })}
          </aside>
        )}
        {!docked && (
          <button type="button" className={`fab patch-fab${chatOpen ? " open" : ""}`} aria-expanded={chatOpen}
            aria-label={chatOpen ? "Close the chat" : "Ask Patch"} onClick={toggleChat}>
            {!chatOpen && <Robot size={58} mood={unread ? "happy" : mood} />}
            <span className="patch-base" aria-hidden="true">{chatOpen && "✕"}</span>
            {unread && <span className="unread-dot" aria-hidden="true" />}
          </button>
        )}
      </div>
      </div>
    </div>
  );
}
