"""Channels and the alert text. Moved from proto (N1-N4), with the senders passed in as `Transports`.

Channels: ntfy (phone push), Telegram (a message from the owner's bot, B57), email (SMTP) and desktop (the OS's own
notification on the machine running the backend). "preview" builds the alert and records it without sending. Every
channel gets the same structured message: never the CVE description, which is untrusted text and shows on a lock screen. Secrets (topic, tokens,
SMTP password) come from .env or the owner's Settings (B26) and never leave the server. A phone alert or an email
carries the link back to the CVE only when a phone can open it (`tap_link`, B26).
"""
import datetime as dt
import html
import ipaddress
import json
import logging
import platform
import shutil
import smtplib
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.errors import AppError

log = logging.getLogger(__name__)

# Without the CVE's priority (the message on its own), the reason's priority. The refresh's alerts (B04) always pass
# the CVE's row, whose priority gives 5/4/3/2 (urgent, high, normal, low).
PRIORITY = {"kev": 5, "kev_recheck": 3, "new": 3, "new_unscored": 2, "now_critical": 4, "due_soon": 4, "overdue": 5}
TITLE = {"kev": "In CISA KEV", "kev_recheck": "Check your fix", "new": "New CVE", "new_unscored": "New CVE, not scored yet",
         "now_critical": "Now critical", "due_soon": "Due in 3 days", "overdue": "Overdue"}
CHANNELS = ("desktop", "email", "ntfy", "telegram")


class NotifyError(AppError):
    code = "notify_failed"


def reachable_from_phone(url: str | None) -> bool:
    """B26: whether a phone could open `url`. Not when its host is this machine (localhost, 127.0.0.0/8, ::1) or
    "any address" (0.0.0.0): on a phone that is the phone itself. A LAN, Tailscale or Cloud Run address is."""
    host = urlsplit(url or "").hostname
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # a host name
    return not (ip.is_loopback or ip.is_unspecified)


def tap_link(click: str | None) -> str | None:
    """The link a phone alert (ntfy) or an email carries: none while the app's address is unreachable from a phone,
    so tapping opens the message in the ntfy app instead of a page that can't load (B26)."""
    return click if click and click.startswith("http") and reachable_from_phone(click) else None


def desktop_command() -> str | None:
    """notify-send on Linux (KDE, GNOME...), osascript on macOS. None elsewhere."""
    if platform.system() == "Darwin":
        return shutil.which("osascript")
    return shutil.which("notify-send")


@dataclass
class Transports:
    """How alerts leave the machine. The real ones by default; tests pass fakes, so no test sends anything."""
    smtp_factory: Callable[[str, int], Any] | None = None  # None: smtplib, chosen by port
    opener: Callable[..., Any] = urllib.request.urlopen  # for ntfy's and Telegram's HTTP requests
    runner: Callable[..., Any] = subprocess.run  # for the desktop command
    # looked up when called, so the tests' guard (conftest.py) can turn the real desktop command off everywhere
    desktop_command: Callable[[], str | None] = lambda: desktop_command()  # noqa: E731
    sleep: Callable[[float], None] = time.sleep  # B55: the wait between ntfy's tries; tests record it instead


class Notifier(Protocol):
    name: str

    def send(self, title: str, body: str, priority: int, tags: list[str], click: str | None) -> None: ...


def format_alert(cve: dict, reason: str, knowledge, app_url: str = "", due: dict | None = None) -> dict:
    """Structured fields only: never the CVE description, which is untrusted and shows on a lock screen.
    `due`: the CVE's row from the priority rules (due_date, no_fix, alert_priority), worded as on the dashboard: "due"
    your due date, or "decide by" when there's no fix yet; its alert priority is the message's (B04). Without it, a
    KEV CVE shows CISA's date as the "KEV deadline" and the reason sets the priority."""
    product = knowledge.products[cve["product"]]
    sev = (cve["severity"] or "unscored").lower() + (f" {cve['cvss']:g}" if cve["cvss"] else "")
    body = f"{cve['id']} · {sev}"
    kev = knowledge.cves.kev.get(cve["id"])
    if due and due.get("due_date"):
        body += f" · {'decide by' if due.get('no_fix') else 'due'} {due['due_date']}"
    elif kev:
        body += f" · KEV deadline {kev['dueDate']}"
    if cve.get("product_source") == "text":
        body += " · possible match"
    priority = (due or {}).get("alert_priority") or (
        PRIORITY[reason] + (1 if reason == "new" and cve["severity"] == "CRITICAL" else 0))
    return {"title": f"{TITLE[reason]}: {product}", "body": body, "priority": priority,
            "tags": [reason, cve["product"]], "click": f"{app_url}/cves/{cve['id']}"}


class PreviewNotifier:
    """Sends nothing: the Settings page's preview, and what tests can look at."""
    name = "preview"

    def send(self, title, body, priority, tags, click) -> None:
        pass


class WaitBudget:
    """B55 (#101): how long sends may wait between tries, in all. One budget is shared by every send it is given to,
    so a run of many messages can't wait many times over."""

    def __init__(self, seconds: float, sleep: Callable[[float], None] = time.sleep):
        self.left, self.sleep = seconds, sleep

    def wait(self, seconds: float) -> bool:
        """Wait `seconds`, or what is left if that is less. False, without waiting: nothing is left."""
        seconds = min(seconds, self.left)
        if seconds <= 0:
            return False
        self.left -= seconds
        self.sleep(seconds)
        return True


TEST_SEND_WAIT = 4.0  # B55: a test send (a web request someone waits on) waits at most this, in all
RUN_WAIT = 60.0  # B55: a refresh, or an access request's alert, waits at most this in all (one budget per run)
# B55: a 429 (ntfy, and Telegram since B57) is tried again inside the same send, at most 3 tries in all
LIMITED_TRIES = 3
LIMITED_BACKOFF = (10.0, 30.0)  # the waits after the first and second 429 when the server says no wait
LIMITED_MAX_WAIT = 30.0  # the server's wait (ntfy's Retry-After, Telegram's retry_after) is honoured up to this
REPLY_MAX = 200  # the server's reply in an error is cut to this many characters


def retry_after(e: urllib.error.HTTPError) -> float | None:
    """The reply's Retry-After in seconds; None without one, or when it's a date (ntfy sends seconds, if anything)."""
    try:
        seconds = float((e.headers or {}).get("Retry-After", ""))
    except (TypeError, ValueError):
        return None
    return seconds if seconds > 0 else None


class NtfyNotifier:
    """Phone push via ntfy: one JSON POST to the server root (checked in ntfy's docs, 2026-10-13). A 429 (ntfy.sh
    limits each IP address, and a shared one like Cloud Run's may be used up by others) is tried again after a short
    wait, within `wait` (B55); every other error fails at once."""
    name = "ntfy"

    def __init__(self, url: str, topic: str, token: str = "", opener=urllib.request.urlopen,
                 wait: WaitBudget | None = None):
        self.url, self.topic, self.token, self.opener = url, topic, token, opener
        self.wait = wait or WaitBudget(0)

    def send(self, title, body, priority, tags, click) -> None:
        payload = {"topic": self.topic, "title": title, "message": body, "priority": priority, "tags": tags}
        if link := tap_link(click):
            payload["click"] = link
        for attempt in range(1, LIMITED_TRIES + 1):
            try:
                self._post(payload)
                return
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == LIMITED_TRIES or not self.wait.wait(
                        min(retry_after(e) or LIMITED_BACKOFF[attempt - 1], LIMITED_MAX_WAIT)):
                    raise NotifyError(self._refused(e)) from e
            except OSError as e:
                raise NotifyError(f"Couldn't reach ntfy at {self.url}: {e}") from e

    def _refused(self, e: urllib.error.HTTPError) -> str:
        """The error, with ntfy's own reply (its code and error text, or the start of a reply that isn't its JSON),
        which tells a rate limit from a ban: a 429 in plain words first. No try count: B41's pill counts the
        next-check tries, and a second count beside it would muddle it."""
        reply = self._reply(e)
        if e.code == 429:
            host = urlsplit(self.url).hostname or self.url
            return f"{host} is limiting this server's address: try again later. ntfy said: {reply}"
        return f"ntfy at {self.url} replied with HTTP {e.code}. ntfy said: {reply}"

    def _reply(self, e: urllib.error.HTTPError) -> str:
        """ntfy's reply, cut to REPLY_MAX characters, with the topic and token blanked out: never in a log line."""
        try:
            raw = e.read().decode("utf-8", "replace").strip()
        except (OSError, AttributeError):
            raw = ""
        try:
            data = json.loads(raw)
            text = f"{data.get('code', e.code)}: {data.get('error', '')}".rstrip(": ")
        except (ValueError, AttributeError):
            text = " ".join(raw.split()) or "nothing"
        for secret in (self.topic, self.token):
            if secret:
                text = text.replace(secret, "…")
        return text if len(text) <= REPLY_MAX else text[:REPLY_MAX - 1] + "…"

    def _post(self, payload: dict) -> None:
        req = urllib.request.Request(self.url + "/", data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        with self.opener(req, timeout=10) as r:
            if r.status >= 300:
                raise NotifyError(f"ntfy replied with HTTP {r.status}.")


TELEGRAM_API = "https://api.telegram.org"
TELEGRAM_RINGS = 4  # this priority and up (high, urgent) rings; below it (normal, low) arrives silently


def telegram_text(title: str, body: str) -> str:
    """The message in Telegram's HTML parse mode: the title in bold, then the body. Only `<`, `>` and `&` need
    escaping there (docs/SOURCE-CHECKS.md), so no title or body can turn into markup."""
    return f"<b>{html.escape(title, quote=False)}</b>\n{html.escape(body, quote=False)}"


class TelegramNotifier:
    """A message from the owner's bot to their chat (B57, #102): one JSON POST to the Bot API's `sendMessage`.
    Telegram limits each bot, not each IP address, so it works from Cloud Run where ntfy.sh's per-IP quota runs out.
    The token is part of the URL, so the URL is never logged, raised or returned."""
    name = "telegram"

    def __init__(self, token: str, chat_id: str, opener=urllib.request.urlopen, wait: WaitBudget | None = None,
                 api: str = TELEGRAM_API):
        self.token, self.chat_id, self.opener, self.api = token, chat_id, opener, api
        self.wait = wait or WaitBudget(0)

    def send(self, title, body, priority, tags, click) -> None:
        payload = {"chat_id": self.chat_id, "text": telegram_text(title, body), "parse_mode": "HTML",
                   "link_preview_options": {"is_disabled": True},
                   # low and normal arrive without a sound; high and urgent ring (DECISIONS.md, B57)
                   "disable_notification": priority < TELEGRAM_RINGS}
        if link := tap_link(click):
            payload["reply_markup"] = {"inline_keyboard": [[{"text": "Open in Patch", "url": link}]]}
        for attempt in range(1, LIMITED_TRIES + 1):
            try:
                self._call("sendMessage", payload)
                return
            except _TelegramRefused as e:
                if e.code != 429 or attempt == LIMITED_TRIES or not self.wait.wait(
                        min(e.retry_after or LIMITED_BACKOFF[attempt - 1], LIMITED_MAX_WAIT)):
                    raise NotifyError(self._refused(e)) from None

    def chats(self) -> list[dict]:
        """Find my chat id (B57): the chats that wrote to the bot lately, newest first, each once: `id` (as
        sendMessage takes it), `name` and `kind` (private, group, supergroup, channel). From `getUpdates`, which
        keeps a message 24 hours and fails while a webhook is set (docs/SOURCE-CHECKS.md). No offset is sent, so
        nothing is marked as read."""
        try:
            result = self._call("getUpdates")
        except _TelegramRefused as e:
            raise NotifyError(self._refused(e, "the request")) from None
        found: dict[str, dict] = {}
        for update in reversed(result if isinstance(result, list) else []):
            for kind in ("message", "edited_message", "channel_post", "my_chat_member"):
                chat = (update.get(kind) or {}).get("chat") if isinstance(update, dict) else None
                if isinstance(chat, dict) and "id" in chat and str(chat["id"]) not in found:
                    name = chat.get("title") or " ".join(filter(None, (chat.get("first_name"), chat.get("last_name"))))
                    found[str(chat["id"])] = {"id": str(chat["id"]), "name": self._scrub(
                        name or (f"@{chat['username']}" if chat.get("username") else "a chat with no name")),
                        "kind": str(chat.get("type", "private"))}
        return list(found.values())

    def _refused(self, e: "_TelegramRefused", what: str = "the message") -> str:
        """The error, with Telegram's own words. No try count, as for ntfy (B55): B41's pill counts the tries."""
        if e.code == 429:
            return f"Telegram is limiting this bot: try again later. Telegram said: {e.said}"
        return f"Telegram refused {what} (HTTP {e.code}). Telegram said: {e.said}"

    def _scrub(self, text: str) -> str:
        """`text` with the token blanked out, cut to REPLY_MAX characters: it goes into errors and log lines."""
        text = " ".join(text.split()).replace(self.token, "…") if self.token else " ".join(text.split())
        return text if len(text) <= REPLY_MAX else text[:REPLY_MAX - 1] + "…"

    def _call(self, method: str, payload: dict | None = None) -> Any:
        """One Bot API call; its `result`. Raises _TelegramRefused with Telegram's reply, or NotifyError when
        Telegram can't be reached. The request (its URL holds the token) never leaves this method: every exception
        is raised `from None`, so no traceback carries it either."""
        req = urllib.request.Request(f"{self.api}/bot{self.token}/{method}",
                                     data=json.dumps(payload).encode() if payload is not None else None,
                                     method="POST" if payload is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        refused = None
        try:
            with self.opener(req, timeout=10) as r:
                reply = _json(r.read())
        except urllib.error.HTTPError as e:
            try:
                raw = e.read()
            except (OSError, AttributeError):
                raw = b""
            reply, refused = _json(raw), e.code
        except OSError as e:
            reason = e.reason if isinstance(e, urllib.error.URLError) else e
            raise NotifyError(f"Couldn't reach Telegram: {self._scrub(str(reason))}") from None
        if refused is None and reply.get("ok"):
            return reply.get("result")
        code = reply.get("error_code") or refused or 0
        said = f"{code}: {reply.get('description') or 'no description'}"
        retry = (reply.get("parameters") or {}).get("retry_after")
        raise _TelegramRefused(refused or code, self._scrub(said),
                               float(retry) if isinstance(retry, int | float) and retry > 0 else None)


class _TelegramRefused(Exception):
    """Telegram answered with an error: the HTTP status (else its `error_code`), its words (scrubbed), and
    `parameters.retry_after` in seconds when it sent one."""

    def __init__(self, code: int, said: str, retry_after: float | None):
        super().__init__(said)
        self.code, self.said, self.retry_after = code, said, retry_after


def _json(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8", "replace") or "{}")
    except (ValueError, AttributeError):
        return {}
    return data if isinstance(data, dict) else {}


class EmailNotifier:
    """Plain-text email over SMTP (STARTTLS on 587, TLS on 465)."""
    name = "email"

    def __init__(self, s, smtp_factory=None):
        self.s = s
        self.smtp_factory = smtp_factory

    def send(self, title, body, priority, tags, click) -> None:
        msg = EmailMessage()
        msg["Subject"] = f"[LLM security] {title}"
        msg["From"] = self.s.alert_email_from or self.s.smtp_user
        msg["To"] = self.s.alert_email_to
        if priority >= 5:
            msg["X-Priority"] = "1"
        msg.set_content("\n".join([
            body, "",
            f"Open it in the app: {link}" if (link := tap_link(click)) else "",
            "",
            "You get this because the product is on your watchlist. Change alerts in the app's Settings.",
        ]))
        try:
            if self.smtp_factory:
                smtp = self.smtp_factory(self.s.smtp_host, self.s.smtp_port)
            elif self.s.smtp_port == 465:
                smtp = smtplib.SMTP_SSL(self.s.smtp_host, 465, timeout=15)
            else:
                smtp = smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=15)
            with smtp:
                if self.s.smtp_starttls and self.s.smtp_port != 465:
                    smtp.starttls()
                if self.s.smtp_user:
                    smtp.login(self.s.smtp_user, self.s.smtp_password)
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as e:
            raise NotifyError(f"Sending the email failed: {type(e).__name__}: {e}") from e


class DesktopNotifier:
    """The OS's own notification, on the machine running the backend (fine for a local app)."""
    name = "desktop"

    def __init__(self, command: str, runner=subprocess.run):
        self.command, self.runner = command, runner

    def send(self, title, body, priority, tags, click) -> None:
        text = body + (f"\n{click}" if click else "")
        if self.command.endswith("osascript"):
            def esc(s: str) -> str:
                return s.replace("\\", "\\\\").replace('"', '\\"')
            args = [self.command, "-e", f'display notification "{esc(text)}" with title "{esc(title)}"']
        else:
            urgency = "critical" if priority >= 5 else "normal" if priority >= 3 else "low"
            # A list of arguments, never a shell string: alert text can't run commands.
            args = [self.command, "--app-name=LLM security", f"--urgency={urgency}", "--icon=dialog-warning", title, text]
        try:
            self.runner(args, check=True, timeout=5, capture_output=True)
        except (OSError, subprocess.SubprocessError) as e:
            raise NotifyError(f"The desktop notification failed: {e}") from e


def mask_email(address: str) -> str:
    name, _, domain = address.partition("@")
    return f"{name[:1]}***@{domain}" if domain else "***"


def channel_status(s, transports: Transports) -> dict:
    """Whether each channel is set up, and how to set it up. Never returns a secret (the email is masked)."""
    cmd = transports.desktop_command()
    email_ready = bool(s.smtp_host and s.alert_email_to)
    # B50 (#95): plain words, no server names (notify-send, SMTP_HOST, NTFY_TOPIC, backend/.env). Only the owner sees
    # these (the Delivery card, a test send's error); README.md maps each to its setting.
    return {
        "desktop": {"configured": bool(cmd),
                    "detail": "On the computer running Patch's server." if cmd
                    else "The computer running Patch's server can't show desktop notifications (Linux and macOS can)."},
        "email": {"configured": email_ready,
                  # B26: the SMTP host is a secret, so it isn't named; the address only masked
                  "detail": f"To {mask_email(s.alert_email_to)} by SMTP, port {s.smtp_port}." if email_ready
                  else "Set the mail server and the address to send to under Email (SMTP), below."},
        "ntfy": {"configured": bool(s.ntfy_topic),
                 "detail": f"To a topic on {s.ntfy_url}." if s.ntfy_topic
                 else "Set a topic (a long random name) under Phone push (ntfy), below."},
        # B57: the token is a secret and the chat id says nothing useful, so neither is shown
        "telegram": {"configured": bool(s.telegram_bot_token and s.telegram_chat_id),
                     "detail": "To your chat, from your bot." if s.telegram_bot_token and s.telegram_chat_id
                     else "Set the bot token and the chat id under Telegram, below."},
    }


def notifier_for(channel: str, s, transports: Transports, wait: WaitBudget | None = None) -> Notifier:
    """The channel's sender. With NOTIFY_DRY_RUN on (the browser check), a set-up channel records only. `wait`: how
    long ntfy or Telegram may wait between tries after a 429 (B55); none, no second try."""
    if channel == "preview":
        return PreviewNotifier()
    status = channel_status(s, transports)[channel]
    if not status["configured"]:
        raise NotifyError(status["detail"], "not_configured")
    if s.notify_dry_run:
        return PreviewNotifier()
    if channel == "ntfy":
        return NtfyNotifier(s.ntfy_url, s.ntfy_topic, s.ntfy_token, opener=transports.opener, wait=wait)
    if channel == "telegram":
        return TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id, opener=transports.opener, wait=wait)
    if channel == "email":
        return EmailNotifier(s, smtp_factory=transports.smtp_factory)
    return DesktopNotifier(transports.desktop_command() or "", runner=transports.runner)


def send_on(channel: str, msg: dict, s, transports: Transports, wait: WaitBudget | None = None) -> dict:
    """Send one message on one channel. The result, never raised: sent, recorded only (not sent, no error), not
    set up, or failed with its error. A failed send is a warning in the server's log, with the error (B55: ntfy's
    or Telegram's own reply is in it; never the topic or a token)."""
    result = {"channel": channel, "sent": False, "error": None, "error_code": None}
    try:
        notifier = notifier_for(channel, s, transports, wait)
        notifier.send(**{k: msg[k] for k in ("title", "body", "priority", "tags", "click")})
    except NotifyError as e:
        result["error"], result["error_code"] = e.message, e.code
        if e.code == "notify_failed":
            log.warning("Sending %r on %s failed: %s", msg["title"], channel, e.message)
    else:
        result["sent"] = notifier.name != "preview"
    return result


def deliver(channel: str, msg: dict, s, transports: Transports, state) -> dict:
    """A test alert (Settings): send on one channel and log the attempt either way, in the alerts log's shape
    (app.alerts) plus this channel's own fields, which the Settings page reads. Re-raises a failure once logged.
    A web request waits for it, so ntfy or Telegram waits at most TEST_SEND_WAIT in all after a 429 (B55)."""
    result = send_on(channel, msg, s, transports, WaitBudget(TEST_SEND_WAIT, transports.sleep))
    entry = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "kind": "test", "cve": None,
             "reason": None, **msg, "alerts": [], "channels": [result], **result}
    state.log_alert(entry)
    if result["error"]:
        raise NotifyError(result["error"], result["error_code"])
    return entry
