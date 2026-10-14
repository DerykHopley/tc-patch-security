"""The snapshot, loaded once: CVEs, KEV, OWASP pages and map, ATLAS, manifest, and (A14) OSV
versions, EPSS scores and the product-match check. Moved from proto.

`CveSource` is the seam for live data later: `FixtureCveSource` now, an NVD-backed one later.
"""
import json
from dataclasses import dataclass, field
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
    osv: dict = field(default_factory=lambda: {"products": {}, "cves": {}})  # per CVE: packages, ranges, fixed
    epss: dict = field(default_factory=lambda: {"scores": {}})  # per CVE: score, percentile, date
    product_check: dict = field(default_factory=lambda: {"cves": {}})  # text-matched CVEs: confirmed/...

    def epss_of(self, cve_id: str) -> dict | None:
        return self.epss["scores"].get(cve_id)

    def product_match(self, cve_id: str) -> str | None:
        """confirmed, conflicting or unknown for a CVE whose product came from description text; else None."""
        checked = self.product_check["cves"].get(cve_id)
        return checked["result"] if checked else None

    def possible_match(self, cve_id: str) -> bool:
        """The product was guessed from text and OSV doesn't confirm it."""
        return self.product_match(cve_id) in ("conflicting", "unknown")

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
        osv=json.loads((FIXTURES / "osv.json").read_text()),
        epss=json.loads((FIXTURES / "epss.json").read_text()),
        product_check=json.loads((FIXTURES / "product_check.json").read_text()),
    )
