"""Channels and the alert text. Moved from proto (N1-N4), with the senders passed in as `Transports`.

Channels: ntfy (phone push), email (SMTP) and desktop (the OS's own notification on the machine running the
backend). "preview" builds the alert and records it without sending. Every channel gets the same structured
message: never the CVE description, which is untrusted text and shows on a lock screen. Secrets (topic, token,
SMTP password) come from .env or the owner's Settings (B26) and never leave the server. A phone alert or an email
carries the link back to the CVE only when a phone can open it (`tap_link`, B26).
"""
import datetime as dt
import ipaddress
import json
import platform
import shutil
import smtplib
import subprocess
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.errors import AppError

# Without the CVE's priority (the message on its own), the reason's priority. The refresh's alerts (B04) always pass
# the CVE's row, whose priority gives 5/4/3/2 (urgent, high, normal, low).
PRIORITY = {"kev": 5, "kev_recheck": 3, "new": 3, "new_unscored": 2, "now_critical": 4, "due_soon": 4, "overdue": 5}
TITLE = {"kev": "In CISA KEV", "kev_recheck": "Check your fix", "new": "New CVE", "new_unscored": "New CVE, not scored yet",
         "now_critical": "Now critical", "due_soon": "Due in 3 days", "overdue": "Overdue"}
CHANNELS = ("desktop", "email", "ntfy")


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
    opener: Callable[..., Any] = urllib.request.urlopen  # for ntfy's HTTP POST
    runner: Callable[..., Any] = subprocess.run  # for the desktop command
    # looked up when called, so the tests' guard (conftest.py) can turn the real desktop command off everywhere
    desktop_command: Callable[[], str | None] = lambda: desktop_command()  # noqa: E731


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
            "tags": [reason, cve["product"]], "click": f"{app_url}/#cve={cve['id']}"}


class PreviewNotifier:
    """Sends nothing: the Settings page's preview, and what tests can look at."""
    name = "preview"

    def send(self, title, body, priority, tags, click) -> None:
        pass


class NtfyNotifier:
    """Phone push via ntfy: one JSON POST to the server root (checked in ntfy's docs, 2026-10-13)."""
    name = "ntfy"

    def __init__(self, url: str, topic: str, token: str = "", opener=urllib.request.urlopen):
        self.url, self.topic, self.token, self.opener = url, topic, token, opener

    def send(self, title, body, priority, tags, click) -> None:
        payload = {"topic": self.topic, "title": title, "message": body, "priority": priority, "tags": tags}
        if link := tap_link(click):
            payload["click"] = link
        req = urllib.request.Request(self.url + "/", data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with self.opener(req, timeout=10) as r:
                if r.status >= 300:
                    raise NotifyError(f"ntfy replied with HTTP {r.status}.")
        except OSError as e:
            raise NotifyError(f"Couldn't reach ntfy at {self.url}: {e}") from e


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
    return {
        "desktop": {"configured": bool(cmd),
                    "detail": f"via {cmd.rsplit('/', 1)[-1]} on the machine running the backend" if cmd
                    else "No notify-send (Linux) or osascript (macOS) found on the backend's machine."},
        "email": {"configured": email_ready,
                  # B26: the SMTP host is a secret, so it isn't named; the address only masked
                  "detail": f"to {mask_email(s.alert_email_to)} by SMTP, port {s.smtp_port}" if email_ready
                  else "The owner sets the SMTP server and the address to send to on Settings, under Email, or "
                  "SMTP_HOST and ALERT_EMAIL_TO in backend/.env."},
        "ntfy": {"configured": bool(s.ntfy_topic),
                 "detail": f"to a topic on {s.ntfy_url}" if s.ntfy_topic
                 else "The owner sets a topic (a long random name) on Settings, under Phone push, or NTFY_TOPIC in "
                 "backend/.env."},
    }


def notifier_for(channel: str, s, transports: Transports) -> Notifier:
    """The channel's sender. With NOTIFY_DRY_RUN on (the browser check), a set-up channel records only."""
    if channel == "preview":
        return PreviewNotifier()
    status = channel_status(s, transports)[channel]
    if not status["configured"]:
        raise NotifyError(status["detail"], "not_configured")
    if s.notify_dry_run:
        return PreviewNotifier()
    if channel == "ntfy":
        return NtfyNotifier(s.ntfy_url, s.ntfy_topic, s.ntfy_token, opener=transports.opener)
    if channel == "email":
        return EmailNotifier(s, smtp_factory=transports.smtp_factory)
    return DesktopNotifier(transports.desktop_command() or "", runner=transports.runner)


def send_on(channel: str, msg: dict, s, transports: Transports) -> dict:
    """Send one message on one channel. The result, never raised: sent, recorded only (not sent, no error), not
    set up, or failed with its error."""
    result = {"channel": channel, "sent": False, "error": None, "error_code": None}
    try:
        notifier = notifier_for(channel, s, transports)
        notifier.send(**{k: msg[k] for k in ("title", "body", "priority", "tags", "click")})
    except NotifyError as e:
        result["error"], result["error_code"] = e.message, e.code
    else:
        result["sent"] = notifier.name != "preview"
    return result


def deliver(channel: str, msg: dict, s, transports: Transports, state) -> dict:
    """A test alert (Settings): send on one channel and log the attempt either way, in the alerts log's shape
    (app.alerts) plus this channel's own fields, which the Settings page reads. Re-raises a failure once logged."""
    result = send_on(channel, msg, s, transports)
    entry = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "kind": "test", "cve": None,
             "reason": None, **msg, "alerts": [], "channels": [result], **result}
    state.log_alert(entry)
    if result["error"]:
        raise NotifyError(result["error"], result["error_code"])
    return entry
