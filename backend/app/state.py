"""Watchlist, CVE statuses, settings and the alerts log in one JSON file, shared by the chat tools, the dashboard
and the Settings page. Moved from proto; settings and the alerts log came with the Settings page (A13).
"""
import datetime as dt
import json
import os
import tempfile
import threading
from pathlib import Path

from app.config import DEFAULT_WATCHLIST, LIBRARY_PRODUCTS
from app.app_settings import AppSettings, DevSettings
from app.errors import InputError
from app.status import DECIDED_BY, LEGACY_NOTE, decision
from app.verdict import USAGES, check_version
ALERTS_LOG_MAX = 50  # kept in the file; the Settings page shows the newest 20


class State:
    def __init__(self, path: Path, knowledge, defaults: AppSettings | None = None,
                 dev_defaults: DevSettings | None = None):
        self.path = path
        self.k = knowledge
        self.defaults = defaults or AppSettings()  # from the environment; saved settings override them
        self.dev_defaults = dev_defaults or DevSettings()
        self._lock = threading.Lock()  # FastAPI runs sync routes in a thread pool

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

    def snapshot(self) -> dict:
        with self._lock:
            return self._load()

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
        out = self.default_fields(pid) | {k: v for k, v in f.items() if v is not None}
        if out["usage"] not in USAGES:
            raise InputError(f"Usage must be one of {', '.join(USAGES)}, not {out['usage']!r}.")
        if out["version"] is not None:
            out["version"] = str(out["version"]).strip() or None
        if out["version"] is not None:
            check_version(self.k.osv["products"].get(pid, {}), self.k.products[pid], out["version"])
        out["internet_facing"] = bool(out["internet_facing"])
        return out

    @staticmethod
    def default_fields(pid: str) -> dict:
        return {"usage": "library" if pid in LIBRARY_PRODUCTS else "self_hosted", "version": None,
                "internet_facing": False}

    @classmethod
    def fields_of(cls, pid: str, data: dict) -> dict:
        """A product's usage, version and internet-facing; the defaults for what a file saved before A15 lacks."""
        return cls.default_fields(pid) | data.get("product_settings", {}).get(pid, {})

    def set_fields(self, name: str, **f) -> dict:
        """Change some of one product's fields (the chat tool); the others stay."""
        pid = self._product(name)
        with self._lock:
            data = self._load()
            new = self._fields(pid, self.fields_of(pid, data) | {k: v for k, v in f.items() if v is not None})
            data["product_settings"] = {**data.get("product_settings", {}), pid: new}
            self._save(data)
            return new

    def set_status(self, cve_id: str, status: str, as_of: str | None = None, via: str = "page",
                   **fields) -> tuple[dict, dict]:
        """The user's decision (A16b): the status plus its record, appended to the CVE's history. Only the user
        decides: the CVEs page, or the chat tool after the user's yes (`via` says which). Returns the CVE and the
        record. Fields per status are checked by app.status.decision."""
        record = decision(status, fields, as_of or dt.date.today().isoformat())
        cve = self.k.cves.get(cve_id)
        if cve is None:
            raise KeyError(cve_id)
        record |= {"decided_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "decided_by": DECIDED_BY,
                   "via": via}
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
        """Saved settings over the defaults, field by field, so a file saved before a field existed still loads."""
        saved = self.snapshot().get("settings", {})
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
        """Saved dev choices over the env defaults, field by field (a file from before a field existed still loads)."""
        saved = self.snapshot().get("dev", {})
        return DevSettings.model_validate(self.dev_defaults.model_dump() | saved)

    def save_dev_settings(self, new: DevSettings) -> DevSettings:
        with self._lock:
            data = self._load()
            data["dev"] = new.model_dump()
            self._save(data)
        return new

    def log_alert(self, entry: dict) -> None:
        with self._lock:
            data = self._load()
            data["alerts_log"] = ([entry] + data.get("alerts_log", []))[:ALERTS_LOG_MAX]
            self._save(data)

    def alerts_log(self) -> list[dict]:
        """Newest first."""
        return self.snapshot().get("alerts_log", [])

    def reset(self) -> None:
        """Back to the default watchlist, no statuses, default settings (dev choices too) and an empty alerts log."""
        with self._lock:
            self.path.unlink(missing_ok=True)

    @staticmethod
    def status_of(cve: dict, data: dict) -> str:
        if cve["product"] not in data["watchlist"]:
            return "not_watched"
        return data["statuses"].get(cve["id"], "open")

    @staticmethod
    def history_of(cve_id: str, data: dict) -> list[dict]:
        """Oldest first. The last record is the current decision."""
        return data.get("history", {}).get(cve_id, [])

    @classmethod
    def decision_of(cls, cve_id: str, data: dict) -> dict | None:
        h = cls.history_of(cve_id, data)
        return h[-1] if h else None
