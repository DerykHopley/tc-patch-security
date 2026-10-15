"""Watchlist, CVE statuses, settings and the alerts log in one JSON file, shared by the chat tools, the dashboard
and the Settings page. Moved from proto; settings and the alerts log came with the Settings page (A13).

Reads go through `State.read()`: your stack as a typed, frozen value (architecture review candidate 4). The file's
JSON shape and the fix-up for files saved before a part existed stay in this module. Writes go through State's
methods; `fork` copies the state for the model check.
"""
import datetime as dt
import json
import os
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from app.config import DEFAULT_WATCHLIST, LIBRARY_PRODUCTS
from app.app_settings import AppSettings, DevSettings
from app.errors import InputError
from app.status import DECIDED_BY, LEGACY_NOTE, decision
from app.verdict import USAGES, check_version
ALERTS_LOG_MAX = 50  # kept in the file; the Settings page shows the newest 20
PROPOSALS_MAX = 50  # proposed changes kept in the file (B21), the newest; older ones are long expired


def _freeze(value):
    """Dicts become read-only mappings and lists tuples, all the way down."""
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value):
    """A fresh, plain copy of a frozen value: the caller may change it without touching the read."""
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


def _upgraded(entry: dict) -> dict:
    """An alerts-log entry in B04's shape. Before B04 the log held test alerts only, one channel each."""
    if "channels" in entry:
        return entry
    result = {k: entry.get(k) for k in ("channel", "sent", "error", "error_code")}
    return {"kind": "test", "cve": None, "reason": None, "alerts": [], **entry, "channels": [result]}


def _default_fields(pid: str) -> dict:
    """A product's fields until you save them, or in a file saved before A15."""
    return {"usage": "library" if pid in LIBRARY_PRODUCTS else "self_hosted", "version": None,
            "internet_facing": False}


@dataclass(frozen=True)
class ProductFields:
    """How you run one product (A15)."""
    usage: str  # one of app.verdict.USAGES
    version: str | None
    internet_facing: bool

    def as_dict(self) -> dict:
        return {"usage": self.usage, "version": self.version, "internet_facing": self.internet_facing}


@dataclass(frozen=True)
class YourStack:
    """Your stack as State read it: a value, so later writes never change it. Build it with State.read()."""
    watchlist: tuple[str, ...]  # watched product ids, in watchlist order
    statuses: Mapping[str, str]  # CVE id → your CVE status; a CVE without one is open
    settings: AppSettings  # the saved settings over the defaults
    dev: DevSettings  # the dev panel's saved choices over the defaults
    alerts_log: tuple[Mapping, ...]  # newest first
    new_since_check: frozenset[str]  # B05: the CVEs your previous check found new (none before a check)
    _fields: Mapping[str, Mapping]  # product id → its saved fields
    _history: Mapping[str, tuple[Mapping, ...]]  # CVE id → its decision records, oldest first

    def watches(self, pid: str) -> bool:
        return pid in self.watchlist

    def fields(self, pid: str) -> ProductFields:
        """A product's usage, version and internet-facing; the defaults for what isn't saved."""
        f = _default_fields(pid) | dict(self._fields.get(pid, {}))
        return ProductFields(usage=f["usage"], version=f["version"], internet_facing=f["internet_facing"])

    def history(self, cve_id: str) -> list[dict]:
        """The CVE's decision records, oldest first (a copy). The last is the current decision."""
        return _thaw(self._history.get(cve_id, ()))

    def decision(self, cve_id: str) -> dict | None:
        """The current decision record (a copy), or None if you never decided."""
        h = self._history.get(cve_id)
        return _thaw(h[-1]) if h else None


class State:
    def __init__(self, path: Path, knowledge, defaults: AppSettings | None = None,
                 dev_defaults: DevSettings | None = None):
        self.path = path
        self.k = knowledge
        self.defaults = defaults or AppSettings()  # from the environment; saved settings override them
        self.dev_defaults = dev_defaults or DevSettings()
        self._lock = threading.Lock()  # FastAPI runs sync routes in a thread pool
        self.approvals = threading.Lock()  # held by app.proposals from a proposal's check to its record (B21)

    def _load(self) -> dict:
        if not self.path.exists():
            return {"watchlist": list(DEFAULT_WATCHLIST), "statuses": {}, "history": {}}
        data = json.loads(self.path.read_text())
        out = {"watchlist": data.get("watchlist", []), "statuses": data.get("statuses", {}),
               "history": data.get("history", {})}
        for key, value in data.items():  # keep parts saved by later tickets (settings, alerts log)
            out.setdefault(key, value)
        for cve_id, status in out["statuses"].items():  # a status saved before decision records (A16b)
            if not out["history"].get(cve_id):
                out["history"][cve_id] = [{"status": status, "justification": None, "reason": None,
                                           "note": LEGACY_NOTE, "review_date": None, "compensating_control": None,
                                           "decided_at": None, "decided_by": None, "via": None}]
        return out

    def _save(self, data: dict) -> None:
        # Write a temp file in the same folder, then rename: a crash never leaves half a file.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, self.path)

    def read(self) -> YourStack:
        """Your stack, from one read of the file."""
        with self._lock:
            data = self._load()
        return YourStack(
            watchlist=tuple(data["watchlist"]), statuses=_freeze(data["statuses"]),
            settings=self._merged_settings(data.get("settings", {})),
            dev=DevSettings.model_validate(self.dev_defaults.model_dump() | data.get("dev", {})),
            alerts_log=_freeze(data.get("alerts_log", [])),
            new_since_check=frozenset(data.get("new_since_check", {}).get("cves", [])), _fields=_freeze(data.get("product_settings", {})),
            _history=_freeze(data["history"]))

    def fork(self, path: Path) -> "State":
        """A copy of this state at `path`, with the same knowledge and defaults: its writes never reach this one."""
        copy = State(path, self.k, self.defaults, self.dev_defaults)
        with self._lock:
            copy._save(self._load())
        return copy

    def _product(self, name: str) -> str:
        pid = self.k.resolve_product(name)
        if not pid:
            raise InputError(f"{name!r} isn't a product I track. Choose from: {', '.join(self.k.products.values())}.")
        return pid

    def watch(self, name: str) -> tuple[list[str], bool]:
        pid = self._product(name)
        with self._lock:
            data = self._load()
            if pid in data["watchlist"]:
                return data["watchlist"], False
            data["watchlist"].append(pid)
            self._save(data)
            return data["watchlist"], True

    def unwatch(self, name: str) -> tuple[list[str], bool]:
        pid = self._product(name)
        with self._lock:
            data = self._load()
            if pid not in data["watchlist"]:
                return data["watchlist"], False
            data["watchlist"].remove(pid)
            self._save(data)
            return data["watchlist"], True

    def set_watchlist(self, names: list[str], fields: dict[str, dict] | None = None) -> list[str]:
        """Replace the watchlist. `fields` (by name): a product's usage, version and internet-facing, replaced as a
        whole (missing ones take the defaults). A product without fields keeps what's saved for it (A15)."""
        pids = list(dict.fromkeys(self._product(n) for n in names))
        checked = {self._product(n): self._fields(self._product(n), f) for n, f in (fields or {}).items()}
        with self._lock:
            data = self._load()
            data["watchlist"] = pids
            if checked:
                data["product_settings"] = {**data.get("product_settings", {}), **checked}
            self._save(data)
            return pids

    # --- Usage, version and internet-facing per product (A15)

    def _fields(self, pid: str, f: dict) -> dict:
        out = _default_fields(pid) | {k: v for k, v in f.items() if v is not None}
        if out["usage"] not in USAGES:
            raise InputError(f"Usage must be one of {', '.join(USAGES)}, not {out['usage']!r}.")
        if out["version"] is not None:
            out["version"] = str(out["version"]).strip() or None
        if out["version"] is not None:
            check_version(self.k.osv["products"].get(pid, {}), self.k.products[pid], out["version"])
        out["internet_facing"] = bool(out["internet_facing"])
        return out

    def check_fields(self, name: str, f: dict) -> dict:
        """One product's fields as set_fields would save them, checked, without saving (B21's preview)."""
        return self._fields(self._product(name), f)

    def set_fields(self, name: str, **f) -> dict:
        """Change some of one product's fields (the chat tool); the others stay."""
        pid = self._product(name)
        with self._lock:
            data = self._load()
            saved = _default_fields(pid) | data.get("product_settings", {}).get(pid, {})
            new = self._fields(pid, saved | {k: v for k, v in f.items() if v is not None})
            data["product_settings"] = {**data.get("product_settings", {}), pid: new}
            self._save(data)
            return new

    def set_status(self, cve_id: str, status: str, as_of: str | None = None, via: str = "page",
                   proposal: str | None = None, sources: list[dict] | None = None, **fields) -> tuple[dict, dict]:
        """The user's decision (A16b): the status plus its record, appended to the CVE's history. Only the user
        decides: the CVEs page, or a change Patch proposed and the user approved (`via` "chat", with the
        `proposal` id, B21; with the `sources` a proposed decision cited, B22). Returns the CVE and the record. Fields per status are checked by app.status.decision."""
        record = decision(status, fields, as_of or dt.date.today().isoformat())
        cve = self.k.cves.get(cve_id)
        if cve is None:
            raise KeyError(cve_id)
        record |= {"decided_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "decided_by": DECIDED_BY,
                   "via": via}
        if proposal:
            record["proposal"] = proposal
        if sources:
            record["sources"] = sources
        with self._lock:
            data = self._load()
            if status == "open":
                data["statuses"].pop(cve["id"], None)
            else:
                data["statuses"][cve["id"]] = status
            data["history"].setdefault(cve["id"], []).append(record)  # append only: never edited or removed
            self._save(data)
        return cve, record

    # --- Settings and the alerts log (A13)

    def settings(self) -> AppSettings:
        """Saved settings over the defaults: read().settings."""
        return self.read().settings

    def _merged_settings(self, saved: dict) -> AppSettings:
        """Field by field, so a file saved before a field existed still loads."""
        merged = self.defaults.model_dump()
        for part, values in merged.items():
            if isinstance(values, dict):
                values |= saved.get(part, {})
            elif part in saved:  # a single value, like the explain level (A19)
                merged[part] = saved[part]
        return AppSettings.model_validate(merged)

    def save_settings(self, new: AppSettings) -> AppSettings:
        with self._lock:
            data = self._load()
            data["settings"] = {**data.get("settings", {}), **new.model_dump()}  # keeps parts other pages saved
            self._save(data)
        return new

    # --- The dev panel's choices (A11): their own part, saved by the Dev page only

    def dev_settings(self) -> DevSettings:
        """Saved dev choices over the env defaults: read().dev."""
        return self.read().dev

    def save_dev_settings(self, new: DevSettings) -> DevSettings:
        with self._lock:
            data = self._load()
            data["dev"] = new.model_dump()
            self._save(data)
        return new

    def log_alert(self, entry: dict) -> None:
        self.log_alerts([entry])

    def log_alerts(self, entries: list[dict]) -> None:
        """Put one run's entries on top of the log, in their order (the first sent first)."""
        with self._lock:
            data = self._load()
            data["alerts_log"] = (entries + data.get("alerts_log", []))[:ALERTS_LOG_MAX]
            self._save(data)

    def alerts_log(self) -> list[dict]:
        """Newest first. Every entry has `kind`, `alerts` and `channels` (B04): a test alert logged before B04 gets
        them from its one channel's fields."""
        return [_upgraded(e) for e in _thaw(self.read().alerts_log)]

    # --- The refresh's alerts (B04): sent once per key, held through quiet hours. In the user's own state, so they
    # move with it when each user has a state (B09).

    def claim_alerts(self, keys: list[str], at: str) -> set[str]:
        """Record the de-duplication keys not seen before and return them: those alerts may go out. The rest were
        sent (or held) already, by an earlier run or before a restart."""
        with self._lock:
            data = self._load()
            alerted = data.setdefault("alerted", {})
            fresh = {k for k in keys if k not in alerted}
            if fresh:
                alerted.update(dict.fromkeys(sorted(fresh), at))
                self._save(data)
            return fresh

    def hold_alerts(self, messages: list[dict]) -> None:
        """Keep alerts found in quiet hours, to send when they end."""
        with self._lock:
            data = self._load()
            data["alerts_held"] = data.get("alerts_held", []) + messages
            self._save(data)

    def take_held_alerts(self) -> list[dict]:
        """The held alerts, oldest first, removed from the state."""
        with self._lock:
            data = self._load()
            held = data.pop("alerts_held", [])
            if held:
                self._save(data)
            return held

    def set_new_since_check(self, cve_ids: list[str], at: str) -> None:
        """The CVEs a good check found new (B05), replacing the previous check's: the CVEs page's "New" chip and
        filter. In the user's own state, so it moves per user with B09."""
        with self._lock:
            data = self._load()
            data["new_since_check"] = {"at": at, "cves": list(cve_ids)}
            self._save(data)

    def clear_alerts(self) -> None:
        """No alerts sent, held or logged, and nothing new (the fake feeds' reset, for the browser check)."""
        with self._lock:
            data = self._load()
            for key in ("alerted", "alerts_held", "alerts_log", "new_since_check"):
                data.pop(key, None)
            self._save(data)

    # --- Proposed changes (B21): app.proposals decides what they do; this keeps them

    def proposal(self, pid: str) -> dict | None:
        with self._lock:
            return self._load().get("proposals", {}).get(pid)

    def save_proposal(self, rec: dict) -> None:
        """Add or replace one proposal; only the newest PROPOSALS_MAX are kept."""
        with self._lock:
            data = self._load()
            kept = {**data.get("proposals", {}), rec["id"]: rec}
            newest = sorted(kept.values(), key=lambda r: r["created_at"], reverse=True)[:PROPOSALS_MAX]
            data["proposals"] = {r["id"]: r for r in newest}
            self._save(data)

    def reset(self) -> None:
        """Back to the default watchlist, no statuses, default settings (dev choices too) and an empty alerts log."""
        with self._lock:
            self.path.unlink(missing_ok=True)
