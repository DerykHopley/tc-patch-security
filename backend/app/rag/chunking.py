"""Turn the snapshot into chunks (R1, R2).

OWASP pages: split at section headings, then into pieces of at most MAX_CHARS at paragraph
boundaries. ATLAS items and CVEs: one document each, split only if long.
"""
import re
from dataclasses import dataclass, field

from app.config import FIXTURES

MAX_CHARS = 600
# A CVE is one document (R2). At 600, 339 of 929 split and left tiny tails ("Fixed in 0.30.0.") that
# match anything through one hash collision. At 1,500 only 3 split.
CVE_MAX_CHARS = 1500
# Link lists and number tables: noise for search. The CWE map is in owasp.json for explain_weakness.
SKIP_SECTIONS = {"references", "reference links", "list of mapped cwes", "score table"}
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    doc_type: str  # owasp_llm | owasp_web | atlas_technique | atlas_mitigation | atlas_case | cve
    title: str
    url: str
    text: str
    section: str | None = None
    date: str | None = None
    # CVE only
    product: str | None = None
    severity: str | None = None
    cvss: float | None = None
    cwes: tuple[str, ...] = field(default=())
    owasp: str | None = None  # A01–A10 for CVEs
    kev: bool = False


def _split_long(text: str, limit: int) -> list[str]:
    """A paragraph over the limit: split at sentence ends, then hard-split as a last resort."""
    parts, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        while len(sentence) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(sentence[:limit])
            sentence = sentence[limit:].lstrip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}" if current else sentence
        if len(candidate) <= limit:
            current = candidate
        else:
            parts.append(current)
            current = sentence
    if current:
        parts.append(current)
    return parts


def pieces(body: str, limit: int = MAX_CHARS) -> list[str]:
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    out, current = [], ""
    for p in paragraphs:
        for part in _split_long(p, limit) if len(p) > limit else [p]:
            candidate = f"{current}\n\n{part}" if current else part
            if len(candidate) <= limit:
                current = candidate
            else:
                out.append(current)
                current = part
    if current:
        out.append(current)
    return out


def sections(markdown: str) -> list[tuple[str | None, str]]:
    """(section name, text) pairs. The section level is one below the page's top heading."""
    levels = [len(m) for m in re.findall(r"^(#+) ", markdown, re.M)]
    if not levels:
        return [(None, markdown)]
    top = min(levels)
    out, name, buf = [], None, []
    for line in markdown.splitlines():
        m = re.match(r"^(#+) (.*)$", line)
        if m and len(m.group(1)) <= top + 1:
            if buf:
                out.append((name, "\n".join(buf)))
            name = None if len(m.group(1)) == top else m.group(2).strip(" .")
            buf = []
        else:
            buf.append(line)
    if buf:
        out.append((name, "\n".join(buf)))
    return out


def chunk_owasp(code: str, kind: str, title: str, url: str, markdown: str) -> list[Chunk]:
    chunks = []
    for name, text in sections(markdown):
        if name and name.lower() in SKIP_SECTIONS:
            continue
        text = _MD_LINK.sub(r"\1", text)  # keep link text, drop URLs
        for piece in pieces(text):
            chunks.append(Chunk(chunk_id=f"{code}#{len(chunks)}", doc_id=code, doc_type=kind, title=title,
                                url=url, text=piece, section=name))
    return chunks


def _doc(doc_id: str, doc_type: str, title: str, url: str, body: str, limit: int = MAX_CHARS, **meta) -> list[Chunk]:
    return [Chunk(chunk_id=f"{doc_id}#{i}", doc_id=doc_id, doc_type=doc_type, title=title, url=url, text=p, **meta)
            for i, p in enumerate(pieces(body, limit))]


def chunk_cve(r: dict, product_name: str) -> list[Chunk]:
    # The header is the first sentence, so a long description never leaves it as a chunk of its own.
    head = f"{r['id']} · {product_name} · {r['severity'] or 'no severity'}."
    return _doc(r["id"], "cve", f"{r['id']} ({product_name})", r["url"], f"{head} {r['description']}", limit=CVE_MAX_CHARS,
                date=r["published"], product=r["product"], severity=r["severity"], cvss=r["cvss"],
                cwes=tuple(r["cwes"]), owasp=r["owasp"], kev=r["kev"])


def build_chunks(knowledge) -> list[Chunk]:
    chunks: list[Chunk] = []
    for code, meta in knowledge.owasp["categories"].items():
        md = (FIXTURES / meta["kind"] / f"{code}.md").read_text(encoding="utf-8")
        chunks += chunk_owasp(code, meta["kind"], meta["title"], meta["url"], md)
    a = knowledge.atlas
    for t in a["techniques"]:
        chunks += _doc(t["id"], "atlas_technique", f"{t['id']} {t['name']}", t["url"], t["description"],
                       date=t["modified"])
    for m in a["mitigations"]:
        chunks += _doc(m["id"], "atlas_mitigation", f"{m['id']} {m['name']}", m["url"], m["description"],
                       date=m["modified"])
    for c in a["case_studies"]:
        chunks += _doc(c["id"], "atlas_case", f"{c['id']} {c['name']}", c["url"], c["summary"], date=c["date"])
    for r in knowledge.cves.all():
        chunks += chunk_cve(r, knowledge.products[r["product"]])
    return chunks
