"""The live data (B02): the snapshot's CVE files, refreshed, kept as whole versions in LIVE_PATH.

    data/live/
      current.json      {"version": 3, "feeds": "real"}: the version the app serves, and which feeds wrote the data
      v000002/, v000003/ cves.json, kev.json, epss.json, osv.json, product_check.json, manifest.json
      refresh.json      last checked and the run log (app.refresh)

Every version has the snapshot's shape, so the dashboard, tools, verdict and priority code read it as they read the
snapshot (app.knowledge.load_knowledge). The first version is a copy of the snapshot. A new version's files are
written first (each whole: temp file, then rename), then current.json is replaced: a reader sees the old version or
the new one, never half of one. The version before the current one is kept, so the next ticket's diff (B04) can
compare them. The files are keys in a store (app.store, B09): locally this folder, deployed a Cloud Storage prefix.

B28: one folder holds one kind of data. Each write records which feeds wrote it (`feeds`: real or fake), and
`check_feeds` refuses the other kind, so made-up CVEs never mix with real ones. A folder with no record (the snapshot
copy, or one written before B28) is accepted, and the next write records its kind.
"""
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from app.config import FIXTURES, ConfigError
from app.store import LocalStore, Store

FILES = ("cves.json", "kev.json", "epss.json", "osv.json", "product_check.json", "manifest.json")
KEEP = 2  # versions kept on disk: the current one and the one before it
_VERSION = re.compile(r"v(\d{6})$")


FEEDS_NAMES = {"real": "the real feeds (FEEDS=real)", "fake": "the fake feeds (FEEDS=fake)"}


class MixedFeeds(ConfigError):
    """The live data was written by the other kind of feeds (B28). The message names the folder and how to start
    fresh."""


class LiveData:
    """The live versions in a store (app.store, B09: the live data is shared, under its own keys). By default the
    store is the folder itself (a LocalStore on `root`), as before B09. With another store (Cloud Storage, deployed),
    `root` is this instance's local copy: a version is copied there once, for load_knowledge to read."""

    def __init__(self, root: Path, store: Store | None = None):
        self.root = Path(root)
        self.store = store if store is not None else LocalStore(self.root)
        self._local = isinstance(self.store, LocalStore) and self.store.root == self.root

    def version(self) -> int:
        """The version the app serves. The first call copies the snapshot in as version 1."""
        current, _ = self.store.read("current.json")
        if current is None:
            return self.write({name: json.loads((FIXTURES / name).read_text()) for name in FILES})
        return current["version"]

    def feeds(self) -> str | None:
        """Which feeds wrote this live data: real, fake, or None (nothing recorded yet: the snapshot copy, or a folder
        from before B28)."""
        current, _ = self.store.read("current.json")
        return (current or {}).get("feeds")

    def where(self) -> str:
        """Where the live data is, for a message: the folder, or the bucket's prefix (deployed, B13)."""
        return str(self.root) if self._local else f"the Cloud Storage bucket's {getattr(self.store, 'prefix', '')}"

    def check_feeds(self, kind: str) -> None:
        """Refuse to serve or refresh this live data with `kind` feeds when the other kind wrote it (B28)."""
        recorded = self.feeds()
        if recorded is None or recorded == kind:
            return
        raise MixedFeeds(
            f"The live data in {self.where()} was written by {FEEDS_NAMES[recorded]}, but this run uses "
            f"{FEEDS_NAMES[kind]}. Patch won't mix the two kinds of data. To start fresh, move it aside "
            f"(for example `mv {self.root} {self.root}-{recorded}`) or set LIVE_PATH to a new folder; the next "
            f"start copies the snapshot in. To keep using it, set FEEDS={recorded}.")

    def folder(self, version: int | None = None) -> Path:
        """The version's folder on this machine (copied from the store first, when the store isn't the folder)."""
        name = f"v{self.version() if version is None else version:06d}"
        folder = self.root / name
        if not self._local and not folder.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            tmp = Path(tempfile.mkdtemp(dir=self.root, prefix=".copy-"))
            for file in FILES:
                (tmp / file).write_text(json.dumps(self.store.read(f"{name}/{file}")[0], indent=1))
            os.replace(tmp, folder)
        return folder

    def read(self, version: int | None = None) -> dict[str, object]:
        """Every file of a version, parsed: {"cves.json": {...}, ...}."""
        name = f"v{self.version() if version is None else version:06d}"
        return {file: self.store.read(f"{name}/{file}")[0] for file in FILES}

    def _versions(self) -> list[int]:
        return sorted({int(m.group(1)) for k in self.store.keys("v") if (m := _VERSION.match(k.split("/")[0]))})

    def write(self, files: dict[str, object], feeds: str | None = None) -> int:
        """Write `files` (every name in FILES) as a new version and serve it. Returns its number. The files go first
        and current.json last, so a reader sees the old version or the new one, never half of one. `feeds`: the kind
        that fetched them (B28), recorded in current.json; None keeps what is recorded."""
        assert set(files) == set(FILES), sorted(files)
        number = max(self._versions(), default=0) + 1
        for name, data in files.items():
            self.store.write(f"v{number:06d}/{name}", data)
        kind = feeds or self.feeds()
        self.store.write("current.json", {"version": number, **({"feeds": kind} if kind else {})})
        for old in self._versions()[:-KEEP]:
            for name in FILES:
                self.store.delete(f"v{old:06d}/{name}")
            if not self._local:
                shutil.rmtree(self.root / f"v{old:06d}", ignore_errors=True)
        return number

    def reset(self) -> int:
        """A new version that is the snapshot again (the fake feeds' reset, for the browser check)."""
        return self.write({name: json.loads((FIXTURES / name).read_text()) for name in FILES})
