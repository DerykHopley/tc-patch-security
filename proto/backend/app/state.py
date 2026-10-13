"""Watchlist, CVE statuses, settings and the alerts log in one JSON file (W1–W4, G1–G4).
Shared by the chat tool, the dashboard and the settings pages."""
import json
import os
import tempfile
import threading
from pathlib import Path

from app.config import DEFAULT_WATCHLIST
from app.errors import InputError
from app.schemas import AppSettings

STATUSES = ("open", "fixed", "not_affected")
ALERTS_LOG_MAX = 50


class State:
    def __init__(self, path: Path, knowledge, defaults: AppSettings | None = None):
        self.path = path
        self.k = knowledge
        self.defaults = defaults or AppSettings()
        self._lock = threading.Lock()  # FastAPI runs sync routes in a thread pool (W2)

    def _load(self) -> dict:
        if not self.path.exists():
            return {"watchlist": list(DEFAULT_WATCHLIST), "statuses": {}}
        data = json.loads(self.path.read_text())
        out = {"watchlist": data.get("watchlist", []), "statuses": data.get("statuses", {})}
        for key in ("settings", "alerts_log"):  # only present once saved, so old files stay valid
            if key in data:
                out[key] = data[key]
        return out

    def _save(self, data: dict) -> None:
        # Write a temp file in the same folder, then rename: a crash never leaves half a file (W2).
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

    def set_watchlist(self, names: list[str]) -> list[str]:
        pids = list(dict.fromkeys(self._product(n) for n in names))
        with self._lock:
            data = self._load()
            data["watchlist"] = pids
            self._save(data)
            return pids

    def set_status(self, cve_id: str, status: str) -> dict:
        if status not in STATUSES:
            raise InputError(f"Status must be one of {', '.join(STATUSES)}, not {status!r}.")
        cve = self.k.cves.get(cve_id)
        if cve is None:
            raise KeyError(cve_id)
        with self._lock:
            data = self._load()
            if status == "open":
                data["statuses"].pop(cve["id"], None)
            else:
                data["statuses"][cve["id"]] = status
            self._save(data)
        return cve

    # --- settings and alerts log

    def settings(self) -> AppSettings:
        """Saved settings over the defaults. A saved file from an older version still loads (G2)."""
        saved = self.snapshot().get("settings", {})
        merged = self.defaults.model_dump()
        for part in ("alerts", "dev"):
            merged[part] |= saved.get(part, {})
        return AppSettings.model_validate(merged)

    def save_settings(self, new: AppSettings) -> AppSettings:
        with self._lock:
            data = self._load()
            data["settings"] = new.model_dump()
            self._save(data)
        return new

    def log_alert(self, entry: dict) -> None:
        with self._lock:
            data = self._load()
            data["alerts_log"] = ([entry] + data.get("alerts_log", []))[:ALERTS_LOG_MAX]
            self._save(data)

    def alerts_log(self) -> list[dict]:
        return self.snapshot().get("alerts_log", [])

    def reset(self) -> None:
        """Back to the default watchlist, no statuses, default settings, empty log (G4)."""
        with self._lock:
            self.path.unlink(missing_ok=True)

    @staticmethod
    def status_of(cve: dict, data: dict) -> str:
        if cve["product"] not in data["watchlist"]:
            return "not_watched"
        return data["statuses"].get(cve["id"], "open")
