"""explain_weakness (T3): a CWE → OWASP category; an ATLAS technique → tactics, mitigations, LLM Top 10."""
import re
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.errors import ToolError
from app.tools.registry import ToolSpec, register


class WeaknessArgs(BaseModel):
    id: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=3, max_length=20)]


def _family(tid: str) -> set[str]:
    """A technique and its parent or sub-techniques roll up together: AML.T0051 ~ AML.T0051.001."""
    return {tid, tid.rsplit(".", 1)[0]} if tid.count(".") == 2 else {tid}


def _cwe(cwe: str, k) -> dict:
    cves = [c for c in k.cves.all() if cwe in c["cwes"]]
    code = k.owasp["cwe_to_web"].get(cwe)
    return {
        "kind": "cwe", "id": cwe, "url": f"https://cwe.mitre.org/data/definitions/{cwe[4:]}.html",
        "category": k.category(code),
        "cves_in_snapshot": len(cves),
        "examples": [{"id": c["id"], "product": k.products[c["product"]], "severity": c["severity"]} for c in cves[:3]],
    }


def _technique(tid: str, k) -> dict:
    a = k.atlas
    tech = next((t for t in a["techniques"] if t["id"] == tid), None)
    if tech is None:
        raise ToolError(f"{tid} isn't an ATLAS technique in version {a['version']}.", "unknown_id")
    fam = _family(tid) | {t["id"] for t in a["techniques"] if t["parent"] == tid}
    return {
        "kind": "atlas_technique", "id": tid, "name": tech["name"], "url": tech["url"],
        "tactics": tech["tactics"], "maturity": tech["maturity"], "description": tech["description"][:800],
        "parent": tech["parent"],
        "subtechniques": [{"id": t["id"], "name": t["name"]} for t in a["techniques"] if t["parent"] == tid],
        "mitigations": [{"id": m["id"], "name": m["name"]} for m in a["mitigations"]
                        if fam & {x for t in m["techniques"] for x in _family(t)}],
        "cited_by_llm_top10": [{"code": code, "title": k.owasp["categories"][code]["title"]}
                               for code, ids in k.owasp["llm_to_atlas"].items()
                               if fam & {x for i in ids for x in _family(i)}],
        "case_studies": sum(1 for c in a["case_studies"] if fam & set(c["techniques"])),
    }


def run(args: WeaknessArgs, deps, ctx) -> dict:
    k = deps.knowledge
    if re.fullmatch(r"CWE-\d+", args.id):
        return _cwe(args.id, k)
    if re.fullmatch(r"AML\.T\d{4}(\.\d{3})?", args.id):
        return _technique(args.id, k)
    raise ToolError(f"{args.id!r} isn't a CWE (like CWE-918) or an ATLAS technique (like AML.T0051).", "unknown_id")


register(ToolSpec(
    name="explain_weakness",
    description="Explain a weakness id: a CWE (e.g. CWE-918) gives its OWASP Top 10 category and CVE count; "
                "an ATLAS technique (e.g. AML.T0051) gives tactics, mitigations and the LLM Top 10 risks citing it.",
    args_model=WeaknessArgs,
    run=run,
))
