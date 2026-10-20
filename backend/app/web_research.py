"""Web research (B08): one search on Tavily, and the daily cap. The research_web tool (app.tools.web) uses it.

- First through Tavily's hosted remote MCP server, with LangChain's MCP adapter (`langchain-mcp-adapters`), the
  course's "remote MCP server" task. If that fails to connect or answer, Tavily's plain search API.
- Fixed settings: basic search, at most 5 results, snippets only (no raw content, no extract), and an exclude list of
  exploit and proof-of-concept sites. A result from one of them is dropped here too, in case Tavily lets one through,
  and so is one whose URL isn't http(s) (`web_link`): the URL becomes a link in the app.
- Only the query is sent. The key goes in the Authorization header, never in a URL, and no log line carries it: the
  MCP SDK and httpx log URLs, and an error's text can hold them, so failures are logged by type only.
- The cap counts searches per day, per user and in total, in memory (spec B: one instance). A failed search isn't
  counted: Tavily charges for answers.
"""
import asyncio
import datetime
import json
import logging
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlsplit

import httpx

from app.config import FIXTURES, Settings

log = logging.getLogger(__name__)

MAX_RESULTS = 5
SNIPPET_CHARS = 500
TIMEOUT_S = 15
MCP_TOOL_NAMES = ("tavily_search", "tavily-search")  # the open-source server's name; the docs' spelling
LIMIT_REACHED = "web research limit reached for today"

# Exploit and proof-of-concept sites: never searched, never shown (spec B: the no-exploit rule covers web sources).
# GitHub isn't here: it hosts proof-of-concept repos, but also the GitHub Advisory Database (DECISIONS.md, B08).
EXCLUDED_DOMAINS = [
    "exploit-db.com", "packetstormsecurity.com", "packetstorm.news", "0day.today", "cxsecurity.com",
    "sploitus.com", "vulnerability-lab.com", "exploitalert.com", "seebug.org",
]


class SearchFailed(Exception):
    """Neither the MCP server nor the plain API answered."""


@dataclass
class Hit:
    title: str
    url: str
    snippet: str
    date: str | None  # the page's date when Tavily gives one (the plain API may; the MCP text never does)

    @property
    def site(self) -> str:
        host = urlsplit(self.url).hostname or ""
        return host.removeprefix("www.")


def excluded(url: str) -> bool:
    """On the exclude list: the host is a listed domain or under one."""
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in EXCLUDED_DOMAINS)


def web_link(url: str) -> bool:
    """A link the app may show: http or https with a host. Anything else (javascript:, data:, a relative path) is
    dropped with its result, because the URL becomes a link's href in the chat and the proposal card."""
    parts = urlsplit(url.strip())
    return parts.scheme.lower() in ("http", "https") and bool(parts.hostname)


def keep(url: str) -> bool:
    """A result the app keeps: a web link not on the exclude list."""
    return web_link(url) and not excluded(url)


def parse_mcp_text(text: str) -> list[Hit]:
    """Tavily MCP's reply. B63: the hosted server answers with Tavily's JSON (`results`: url, title, content,
    published_date; *checked* 2026-10-20). The older layout (tavily-mcp src/format-results.ts) is labelled lines per
    result, `Title:`, `URL:`, `Content:` (and others we don't use); a line without a label continues the field before
    it. Both are read, so a change back doesn't break search again."""
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return [Hit(r.get("title") or r["url"], r["url"], (r.get("content") or "").strip(),
                    r.get("published_date") or None)
                for r in data["results"] if isinstance(r, dict) and r.get("url")]
    hits: list[dict] = []
    current: dict | None = None
    key = None
    labels = {"Title": "title", "URL": "url", "Content": "content", "ID": None, "Raw Content": None, "Favicon": None}
    for line in text.splitlines():
        label, sep, value = line.partition(": ")
        if sep and label in labels:
            key = labels[label]
            if key == "title" or (key == "url" and (current is None or "url" in current)):
                current = {}
                hits.append(current)
            if key and current is not None:
                current[key] = value
        elif line.strip() and key and current is not None:
            current[key] = f"{current[key]}\n{line}"
    return [Hit(h.get("title") or h["url"], h["url"], (h.get("content") or "").strip(), None)
            for h in hits if h.get("url")]


@dataclass
class DailyCap:
    """Searches today, per user and in total. `today` is the real date (UTC), not the snapshot's as-of date: the cap
    guards real credits."""
    total: int
    per_user: int
    today: Callable[[], str] = lambda: datetime.datetime.now(datetime.UTC).date().isoformat()
    _day: str = ""
    _users: dict[str, int] = field(default_factory=dict)

    def _roll(self) -> None:
        if self._day != (day := self.today()):
            self._day, self._users = day, {}

    def allows(self, user: str) -> bool:
        self._roll()
        return sum(self._users.values()) < self.total and self._users.get(user, 0) < self.per_user

    def count(self, user: str) -> None:
        self._roll()
        self._users[user] = self._users.get(user, 0) + 1

    def left(self, user: str) -> int:
        self._roll()
        return max(0, min(self.total - sum(self._users.values()), self.per_user - self._users.get(user, 0)))


class WebResearch:
    """Tavily search with the fixed settings, and the daily cap. Built only when there's a key."""

    def __init__(self, settings: Settings, cap: DailyCap | None = None):
        self._key = settings.tavily_api_key
        self.mcp_url = settings.tavily_mcp_url
        self.api_url = settings.tavily_api_url.rstrip("/")
        self.cap = cap or DailyCap(settings.web_research_daily_cap, settings.web_research_user_daily_cap)

    def _args(self, query: str) -> dict:
        return {"query": query, "search_depth": "basic", "max_results": MAX_RESULTS, "include_raw_content": False,
                "exclude_domains": list(EXCLUDED_DOMAINS)}

    def search(self, query: str) -> tuple[list[Hit], str]:
        """The hits (excluded sites dropped, snippets cut) and how they came: "mcp" or "api"."""
        try:
            hits, via = asyncio.run(asyncio.wait_for(self._mcp(query), TIMEOUT_S)), "mcp"
        except Exception as e:  # noqa: BLE001  any failure: connection, protocol, tool error, timeout
            log.warning("Tavily MCP search failed (%s); using the plain search API", type(e).__name__)
            hits, via = self._api(query), "api"
        kept = [Hit(h.title, h.url, h.snippet[:SNIPPET_CHARS], h.date) for h in hits if keep(h.url)]
        return kept[:MAX_RESULTS], via

    async def _mcp(self, query: str) -> list[Hit]:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        from langchain_mcp_adapters.tools import load_mcp_tools

        client = MultiServerMCPClient({"tavily": {
            "transport": "streamable_http", "url": self.mcp_url, "timeout": TIMEOUT_S,
            "headers": {"Authorization": f"Bearer {self._key}"}}}, handle_tool_errors=False)
        async with client.session("tavily") as session:
            tools = {t.name: t for t in await load_mcp_tools(session)}
            tool = next((tools[n] for n in MCP_TOOL_NAMES if n in tools), None)
            if tool is None:
                raise SearchFailed(f"no search tool among {sorted(tools)}")
            content = await tool.ainvoke(self._args(query))
        text = content if isinstance(content, str) else "\n".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
        hits = parse_mcp_text(text)
        if not hits and text.strip() and '"results": []' not in text and '"results":[]' not in text:
            # B63: a reply we can't read is a failure, not "no results": the plain API gets a turn
            raise SearchFailed("an MCP reply with no results Patch could read")
        return hits

    def _api(self, query: str) -> list[Hit]:
        try:
            r = httpx.post(f"{self.api_url}/search", json=self._args(query), timeout=TIMEOUT_S,
                           headers={"Authorization": f"Bearer {self._key}"})
            r.raise_for_status()
            results = r.json()["results"]
        except Exception as e:  # noqa: BLE001
            log.warning("Tavily search API failed (%s)", type(e).__name__)
            raise SearchFailed() from None
        return [Hit(x.get("title") or x["url"], x["url"], (x.get("content") or "").strip(),
                    x.get("published_date") or None) for x in results if x.get("url")]


class CannedWeb:
    """The saved web results (fixtures/web_canned.json) in place of Tavily, for the model check's web question (B22):
    every run, and every model, sees the same pages, with no key, no network and no credits. The same filters apply
    as to a real search (excluded sites dropped, snippets cut). Never used by the chat."""

    def __init__(self):
        self.cap = DailyCap(total=10**6, per_user=10**6)
        self._results = json.loads((FIXTURES / "web_canned.json").read_text())["results"]

    def search(self, query: str) -> tuple[list[Hit], str]:
        hits = [Hit(r["title"], r["url"], r["content"][:SNIPPET_CHARS], r.get("published_date"))
                for r in self._results if keep(r["url"])]
        return hits[:MAX_RESULTS], "canned"
