"""The live data (B02): the snapshot's CVE files, refreshed, kept as whole versions in LIVE_PATH.

    data/live/
      current.json      {"version": 3}: the version the app serves
      v000002/, v000003/ cves.json, kev.json, epss.json, osv.json, product_check.json, manifest.json
      refresh.json      last checked and the run log (app.refresh)

Every version has the snapshot's shape, so the dashboard, tools, verdict and priority code read it as they read the
snapshot (app.knowledge.load_knowledge). The first version is a copy of the snapshot. A new version is written whole
into a temp folder and renamed, then current.json is replaced: a reader sees the old version or the new one, never
half of one. The version before the current one is kept, so the next ticket's diff (B04) can compare them.
"""
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from app.config import FIXTURES

FILES = ("cves.json", "kev.json", "epss.json", "osv.json", "product_check.json", "manifest.json")
KEEP = 2  # versions kept on disk: the current one and the one before it
_VERSION = re.compile(r"v(\d{6})$")


def write_json(path: Path, data) -> None:
    """Write a temp file in the same folder, then rename: a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


class LiveData:
    def __init__(self, root: Path):
        self.root = Path(root)

    @property
    def _current(self) -> Path:
        return self.root / "current.json"

    def version(self) -> int:
        """The version the app serves. The first call copies the snapshot in as version 1."""
        if not self._current.exists():
            return self.write({name: json.loads((FIXTURES / name).read_text()) for name in FILES})
        return json.loads(self._current.read_text())["version"]

    def folder(self, version: int | None = None) -> Path:
        return self.root / f"v{self.version() if version is None else version:06d}"

    def read(self, version: int | None = None) -> dict[str, object]:
        """Every file of a version, parsed: {"cves.json": {...}, ...}."""
        folder = self.folder(version)
        return {name: json.loads((folder / name).read_text()) for name in FILES}

    def _versions(self) -> list[int]:
        return sorted(int(m.group(1)) for p in self.root.glob("v*") if (m := _VERSION.match(p.name)))

    def write(self, files: dict[str, object]) -> int:
        """Write `files` (every name in FILES) as a new version and serve it. Returns its number."""
        assert set(files) == set(FILES), sorted(files)
        self.root.mkdir(parents=True, exist_ok=True)
        number = max(self._versions(), default=0) + 1
        tmp = Path(tempfile.mkdtemp(dir=self.root, prefix=".new-"))
        for name, data in files.items():
            (tmp / name).write_text(json.dumps(data, indent=1))
        os.replace(tmp, self.root / f"v{number:06d}")
        write_json(self._current, {"version": number})
        for old in self._versions()[:-KEEP]:
            shutil.rmtree(self.root / f"v{old:06d}", ignore_errors=True)
        return number

    def reset(self) -> int:
        """A new version that is the snapshot again (the fake feeds' reset, for the browser check)."""
        return self.write({name: json.loads((FIXTURES / name).read_text()) for name in FILES})
