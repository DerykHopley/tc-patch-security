"""The fixture snapshot, loaded once: CVEs, KEV, OWASP pages and map, ATLAS, manifest.

`CveSource` is the seam for live data later: `FixtureCveSource` now, an NVD-backed one later.
"""
import json
from dataclasses import dataclass
from typing import Protocol

from app.config import FIXTURES

SEVERITY_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


class CveSource(Protocol):
    def get(self, cve_id: str) -> dict | None: ...
    def all(self) -> list[dict]: ...


class FixtureCveSource:
    def __init__(self, path=FIXTURES / "cves.json", kev_path=FIXTURES / "kev.json"):
        data = json.loads(path.read_text())
        self.products: dict[str, str] = data["products"]  # id -> display name
        self._rows = data["cves"]
        self._by_id = {r["id"]: r for r in self._rows}
        self.kev: dict[str, dict] = {k["cveID"]: k for k in json.loads(kev_path.read_text())}

    def get(self, cve_id: str) -> dict | None:
        return self._by_id.get(cve_id.upper())

    def all(self) -> list[dict]:
        return self._rows


@dataclass
class Knowledge:
    cves: CveSource
    owasp: dict  # categories, cwe_to_web, llm_to_atlas
    atlas: dict  # version, tactics, techniques, mitigations, case_studies
    manifest: dict

    @property
    def products(self) -> dict[str, str]:
        return self.cves.products

    def category(self, code: str | None) -> dict | None:
        if not code or code not in self.owasp["categories"]:
            return None
        c = self.owasp["categories"][code]
        return {"code": code, "title": c["title"], "url": c["url"]}

    def resolve_product(self, name: str | None) -> str | None:
        """Case-insensitive, with simple aliases: 'Open WebUI', 'openwebui' -> 'open-webui' (S3)."""
        if not name:
            return None
        key = "".join(ch for ch in str(name).lower() if ch.isalnum())
        for pid, display in self.products.items():
            if key in ("".join(ch for ch in pid if ch.isalnum()), "".join(ch for ch in display.lower() if ch.isalnum())):
                return pid
        return None


def load_knowledge() -> Knowledge:
    return Knowledge(
        cves=FixtureCveSource(),
        owasp=json.loads((FIXTURES / "owasp.json").read_text()),
        atlas=json.loads((FIXTURES / "atlas.json").read_text()),
        manifest=json.loads((FIXTURES / "manifest.json").read_text()),
    )
