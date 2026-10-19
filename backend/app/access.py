"""Sign-up requests the owner approves in Patch (B38, #81).

Sign-up is open in Clerk (Public mode), so anyone can make an account on Patch's page. Patch lets an account in only
once the owner approves it. Each person's request is one entry in ACCESS, a small record next to the users' state
(locally `state-users/access.users.json`, deployed `users/access.users.json` in the bucket):

    {"<clerk user id>": {"status": "waiting" | "approved" | "refused", "at": <when it last changed>,
                         "by": <the owner's id, or None for the person's own request>, "requested_at": ...,
                         "note": <optional, at most 280 characters>, "alerted": <the alert was sent: once>,
                         "role": "viewer" | "trusted" | "reviewer" (B45; missing: viewer)}}

No name, no email: the Requests card asks Clerk's Backend API for those when it opens (`clerk_people.py`).

- No entry: the person hasn't asked yet ("none"). `request` makes a waiting entry and says it's new, so the caller
  alerts the owner once. Asking again changes nothing; a refused person stays refused (no new alert).
- The owner is always approved and has no entry.
- `adopt_existing` (once, on the first start with this record): everyone Patch already knew (signed in before, or
  saved state) is approved, since in Restricted mode they were invited by the owner.

Roles (B45, #90): the owner gives each approved person a role, kept in their entry. A missing role is a Viewer (so
everyone approved before roles is one). The owner is OWNER from the environment, never a stored role: nobody can make
themselves owner, or lock the owner out, from inside the app. `role` reads the record on every call (no cache), so a
change takes effect on the person's next request, on any instance.

Writes use the store's version check, so two requests (or two instances) never lose each other's change.
"""
import datetime as dt
import re
import threading
from collections.abc import Callable, Iterable

from app.config import DEFAULT_USER, USER_ID
from app.store import Conflict, Store

ACCESS = "access.users.json"  # the dot keeps it from being read as a user's state (a user id has none)
STATUSES = ("waiting", "approved", "refused")
ROLES = ("viewer", "trusted", "reviewer")  # B45: the stored roles; "owner" is OWNER, never stored
DEFAULT_ROLE = "viewer"
NOTE_MAX = 280
_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")  # control characters but the line break


def clean_note(note: str | None) -> str | None:
    """Plain text: control characters dropped (a line break stays), trimmed, None when empty. The length is checked
    by the route (at most NOTE_MAX after trimming)."""
    text = _CONTROL.sub("", note or "").strip()
    return text or None


class Access:
    def __init__(self, store: Store, owner: str, clock: Callable[[], dt.datetime]):
        self.store, self.owner, self.clock = store, owner, clock
        self.enabled = False  # sign-in on: only then does anyone need approving (build_deps turns it on)
        self._approved: set[str] = set()  # approved users this process has seen: no store read per request
        self._lock = threading.Lock()

    def _now(self) -> str:
        return self.clock().astimezone(dt.UTC).isoformat(timespec="seconds")

    def all(self) -> dict[str, dict]:
        return self.store.read(ACCESS)[0] or {}

    def entry(self, user: str) -> dict | None:
        return self.all().get(user)

    def status(self, user: str) -> str:
        """approved, waiting, refused, or none (hasn't asked). Sign-in off, or the owner: approved."""
        if not self.enabled or user == self.owner:
            return "approved"
        if user in self._approved:
            return "approved"
        found = self.entry(user)
        status = found["status"] if found else "none"
        if status == "approved":
            self._approved.add(user)
        return status

    def role(self, user: str) -> str:
        """owner (OWNER; with sign-in off, the one local user), else an approved person's stored role: viewer, trusted
        or reviewer. Anyone else (waiting, refused, no entry) counts as a viewer; the API refuses them anyway."""
        if user == self.owner:
            return "owner"
        found = self.entry(user)
        if not found or found["status"] != "approved":
            return DEFAULT_ROLE
        return found.get("role") or DEFAULT_ROLE

    def _change(self, change: Callable[[dict], object]):
        """Read, change, write with the version check; on a conflict read again and redo the change."""
        while True:
            data, version = self.store.read(ACCESS)
            data = data or {}
            result = change(data)
            try:
                self.store.write(ACCESS, data, if_version=version)
            except Conflict:
                continue
            with self._lock:
                self._approved = {u for u in self._approved if data.get(u, {}).get("status") == "approved"}
            return result

    def request(self, user: str, note: str | None) -> tuple[dict, bool]:
        """The person asks to be let in. Returns their entry and whether it's a new request (alert the owner)."""
        def change(data: dict):
            if user in data:
                return data[user], False
            now = self._now()
            data[user] = {"status": "waiting", "at": now, "by": None, "requested_at": now, "note": note,
                          "alerted": False}
            return data[user], True
        return self._change(change)

    def mark_alerted(self, user: str) -> None:
        def change(data: dict):
            if user in data:
                data[user]["alerted"] = True
        self._change(change)

    def set(self, user: str, status: str | None, by: str, role: str | None = None) -> dict:
        """The owner approves, refuses, or undoes a refusal, and (B45) sets the role: either or both. KeyError: no
        request from this user."""
        if status is not None and status not in STATUSES:
            raise ValueError(status)
        if role is not None and role not in ROLES:
            raise ValueError(role)

        def change(data: dict):
            entry = data[user]  # KeyError: nobody to change
            if status is not None and entry["status"] != status:
                entry.update(status=status, at=self._now(), by=by)
            if role is not None:
                entry["role"] = role
            return entry
        return self._change(change)

    def remove(self, user: str) -> None:
        """The owner removes the person: their entry and note go. They can ask again (one more alert)."""
        self._change(lambda data: data.pop(user, None))
        with self._lock:
            self._approved.discard(user)

    def adopt_existing(self, ids: Iterable[str]) -> None:
        """Once, when the record doesn't exist yet: everyone Patch already knows is approved. Create-only, so a
        second start (or a second instance) never adds anyone."""
        if self.store.read(ACCESS)[0] is not None:
            return
        now = self._now()
        data = {u: {"status": "approved", "at": now, "by": None, "requested_at": None, "note": None,
                    "alerted": False, "migrated": True}
                for u in ids if USER_ID.fullmatch(u) and u not in (self.owner, DEFAULT_USER)}
        try:
            self.store.write(ACCESS, data, if_version=None)
        except Conflict:
            pass
