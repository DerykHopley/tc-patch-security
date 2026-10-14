"""lookup_cve (T2): one CVE from the snapshot, with OWASP, KEV and watchlist context."""
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.errors import ToolError
from app.rag.chunking import chunk_cve
from app.rag.pipeline import to_source
from app.state import State
from app.tools.registry import ToolSpec, register


class CveArgs(BaseModel):
    cve_id: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"(?i)^CVE-\d{4}-\d{4,}$")]


def run(args: CveArgs, deps, ctx) -> dict:
    k = deps.knowledge
    cve = k.cves.get(args.cve_id)
    if cve is None:
        raise ToolError(f"{args.cve_id} isn't in my snapshot ({len(k.cves.all())} CVEs for "
                        f"{len(k.products)} LLM products, as of {deps.settings.as_of}).", "cve_not_in_snapshot")
    kev = k.cves.kev.get(cve["id"])
    status = State.status_of(cve, deps.state.snapshot())
    source = to_source(len(ctx.sources) + 1, chunk_cve(cve, k.products[cve["product"]])[0], None)
    ctx.sources.append(source)
    return {
        "n": source.n,
        "id": cve["id"], "product": k.products[cve["product"]], "published": cve["published"],
        "severity": cve["severity"], "cvss": cve["cvss"], "cwes": cve["cwes"],
        "owasp": k.category(cve["owasp"]), "description": cve["description"], "url": cve["url"],
        "kev": None if not kev else {"date_added": kev["dateAdded"], "due": kev["dueDate"],
                                     "ransomware": kev["knownRansomwareCampaignUse"],
                                     "required_action": kev["requiredAction"]},
        "watch_status": status,
    }


register(ToolSpec(
    name="lookup_cve",
    description="Look up one CVE by id (e.g. CVE-2024-8309): severity, CWEs, OWASP category, CISA KEV status, "
                "and whether it's open on the user's watchlist.",
    args_model=CveArgs,
    run=run,
))
