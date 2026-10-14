"""FakeLLM: the test-only model, scripted, free, same every run (L1). Moved from proto. Reads fixtures/fake_script.json.

Tool choice, rewrites and filters are scripted. The answer text is a template filled from the
real tool results in `messages`, so retrieval and tools are tested for real.

Unscripted questions: a CVE id → lookup_cve, then search_security for how to prevent its OWASP
category (what the dashboard's "Ask about this" sends). A CWE or ATLAS id → explain_weakness.
Anything else → search_security with the question as is.

Explain levels (A19): the level is read from the system prompt's level line, as a real model would read it. A script
with `answers` has one template per level, with the same facts and citations.
"""
import json
import re

from app import guard
from app.config import FIXTURES
from app.llm.base import LLMReply, QueryPlan, ToolCall

NOTHING_FOUND = "I found nothing relevant in the knowledge base for that question."
LEVEL_LINE = re.compile(r"^Explain level: (simple|normal|deep dive)\.", re.M)
SEVERITY_WORD = {"CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium", "LOW": "low"}


def _tokens(text: str) -> int:
    return max(1, len(text) // 4)  # estimate: characters / 4


def _first_sentence(text: str) -> str:
    body = re.sub(r"^CVE-\S+ · [^·]+ · \S+\.\s*", "", text)  # skip a CVE chunk's header sentence
    body = re.sub(r"^[#*\-\s]+", "", " ".join(body.split()))
    return re.split(r"(?<=[.!?])\s", body, maxsplit=1)[0][:240]


def _bullets(sources: list[dict], limit: int) -> str:
    if not sources:
        return NOTHING_FOUND
    out = []
    for s in sources[:limit]:
        if s["doc_type"] == "cve":
            tags = " · ".join(x for x in (s.get("severity"), "in CISA KEV" if s.get("kev") else None, s.get("date")) if x)
            out.append(f"- **{s['title']}** ({tags}): {_first_sentence(s['text'])} [{s['n']}]")
        else:
            where = f" — {s['section']}" if s.get("section") else ""
            out.append(f"- **{s['title']}**{where}: {_first_sentence(s['text'])} [{s['n']}]")
    return "\n".join(out)


def _cve_card(c: dict) -> str:
    sev = f"{SEVERITY_WORD.get(c['severity'], 'unscored')} severity" + (f", CVSS {c['cvss']:g}" if c["cvss"] else "")
    lines = [f"**{c['id']}** in {c['product']} ({sev}, published {c['published']}) [{c['n']}]",
             "", c["description"]]
    if c["owasp"]:
        lines.append(f"\nWeakness: {', '.join(c['cwes']) or 'none recorded'}, which OWASP files under "
                     f"**{c['owasp']['title']}**.")
    if c["kev"]:
        lines.append(f"\n**Exploited in the wild:** CISA added it to KEV on {c['kev']['date_added']} "
                     f"(KEV deadline {c['kev']['deadline']}). {c['kev']['required_action']}")
    status = {"open": "It's **open** on your watchlist.", "fixed": "You marked it **fixed**.",
              "not_affected": "You marked it **not affected**.",
              "accepted": "You **accepted** the risk", "not_watched": "Its product isn't on your watchlist."
              }[c["watch_status"]]
    d = c.get("decision")
    if c["watch_status"] == "accepted" and d:
        status += f" ({d['reason']}); review {'due now' if c['review_due'] else 'on ' + str(d['review_date'])}."
    lines.append(f"\n{status}")
    if c.get("no_fix") and c["watch_status"] == "open":
        lines.append("\nOSV lists **no fixed version** yet, so it isn't overdue: decide by its due date whether to "
                     "mitigate, replace the product, or accept the risk on the CVEs page.")
    return "\n".join(lines)


WHO_ACTS = {"you": "you: upgrade it", "upstream": "upstream: the package that brings it in has to update",
            "vendor": "the vendor: they run it for you"}
VERDICT_WORD = {"affected": "affected", "not_affected": "not affected", "unknown": "unknown"}


def _verdict_line(v: dict) -> str:
    """One CVE's verdict from check_affected (A15). Advice: the status is the user's to change."""
    fixed = f" Fixed in {v['fixed_version']}." if v["fixed_version"] else ""
    line = (f"**{v['id']}** in {v['product']} [{v['n']}]: **{VERDICT_WORD[v['verdict']]}** by the version check. "
            f"{v['reason'][0].upper()}{v['reason'][1:]}.{fixed} Who acts: {WHO_ACTS[v['who_acts']]}.")
    if v["verdict"] == "not_affected" and v["watch_status"] == "open":
        line += " It stays open until you mark it: the CVEs page offers \"Mark not affected?\"."
    elif v["reason"] == "no version given":
        line += " Add your version in the watchlist editor and I can check."
    return line


def _verdict_counts(p: dict) -> str:
    c = p["counts"]
    head = (f"{p['product']} ({p['usage']}, {'version ' + p['version'] if p['version'] else 'no version given'}): "
            f"{p['open']} open CVEs, {c['affected']} affected, {c['unknown']} unknown, {c['not_affected']} not "
            f"affected by the version check.")
    rows = [f"- {x['id']}: {VERDICT_WORD[x['verdict']]}, {x['reason']}" for x in p["cves"][:5]]
    return "\n".join([head, *rows])


def _weakness(w: dict) -> str:
    if w["kind"] == "cwe":
        cat = w["category"]
        head = (f"**{w['id']}** is in OWASP Top 10 2025 **{cat['title']}**." if cat
                else f"**{w['id']}** isn't in any OWASP Top 10 2025 category's list.")
        ex = ", ".join(f"{e['id']} ({e['product']})" for e in w["examples"])
        return f"{head} {w['cves_in_snapshot']} CVEs in my snapshot have it" + (f", for example {ex}." if ex else ".")
    lines = [f"**{w['id']} {w['name']}** (MITRE ATLAS; tactics: {', '.join(w['tactics']) or 'none'}; "
             f"maturity: {w['maturity']})", "", _first_sentence(w["description"])]
    if w["subtechniques"]:
        lines.append("\nSub-techniques: " + ", ".join(f"{s['id']} {s['name']}" for s in w["subtechniques"]) + ".")
    if w["mitigations"]:
        lines.append("\nMitigations: " + ", ".join(f"{m['id']} {m['name']}" for m in w["mitigations"]) + ".")
    if w["cited_by_llm_top10"]:
        lines.append("\nOWASP LLM Top 10 risks that cite it: "
                     + ", ".join(c["title"] for c in w["cited_by_llm_top10"]) + ".")
    lines.append(f"\nIt appears in {w['case_studies']} ATLAS case studies.")
    return "\n".join(lines)


def _level(messages: list[dict]) -> str:
    system = next((m["content"] or "" for m in messages if m["role"] == "system"), "")
    found = LEVEL_LINE.search(system)
    return found.group(1).replace(" ", "_") if found else "normal"


class FakeLLM:
    name = "fake"

    def __init__(self, script_path=FIXTURES / "fake_script.json"):
        self.scripts = json.loads(script_path.read_text())["scripts"]

    def label(self) -> str:
        return "FakeLLM (scripted)"

    def examples(self) -> list[dict]:
        return [{"id": s["id"], "question": s["question"]} for s in self.scripts]

    def _match(self, text: str) -> dict | None:
        low = text.lower()
        for s in self.scripts:
            if all(k in low for k in s["keywords"]):
                return s
            # translate() gets the search query, which may not repeat every keyword (Q2).
            if any(tc["name"] == "search_security" and tc["args"]["query"].lower() == low.strip()
                   for tc in s["tool_calls"]):
                return s
        return None

    def translate(self, question: str) -> tuple[QueryPlan, LLMReply]:
        script = self._match(question)
        if script and "plan" in script:
            plan = QueryPlan(**script["plan"])
        else:
            plan = QueryPlan(semantic_query=question, rewrites=[], filters={})
        reply = LLMReply(input_tokens=_tokens(question) + 100, output_tokens=_tokens(plan.model_dump_json()),
                         estimated=True)
        return plan, reply

    @staticmethod
    def _default_calls(question: str) -> list[dict]:
        if m := guard.CVE_RE.search(question):
            return [{"name": "lookup_cve", "args": {"cve_id": m.group(0).upper()}}]
        if m := (guard.CWE_RE.search(question) or guard.ATLAS_RE.search(question)):
            return [{"name": "explain_weakness", "args": {"id": m.group(0).upper()}}]
        return [{"name": "search_security", "args": {"query": question}}]

    def step(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        question = messages[last_user]["content"]
        script = self._match(question)
        tool_msgs = [m for m in messages[last_user:] if m["role"] == "tool"]
        n_input = _tokens(json.dumps(messages) + json.dumps(tools))

        calls = None
        if not tool_msgs:
            calls = script["tool_calls"] if script else self._default_calls(question)
        elif script is None and len(tool_msgs) == 1:
            # Unscripted CVE question: after the lookup, search for how to prevent its kind of bug.
            data = json.loads(guard.unwrap(tool_msgs[0]["content"]))
            if "watch_status" in data:
                # No product name in the query: it would pull in more CVEs instead of the guidance.
                topic = data["owasp"]["title"].split(" ", 1)[-1] if data["owasp"] else "this vulnerability"
                calls = [{"name": "search_security", "args": {"query": f"How to prevent {topic}"}}]
        if calls:
            tool_calls = [ToolCall(id=f"call_{len(tool_msgs)}_{i}", name=c["name"], args=c["args"])
                          for i, c in enumerate(calls)]
            return LLMReply(tool_calls=tool_calls, input_tokens=n_input,
                            output_tokens=_tokens(json.dumps([t.model_dump() for t in tool_calls])), estimated=True)

        content = self._answer(script, tool_msgs, _level(messages))
        return LLMReply(content=content, input_tokens=n_input, output_tokens=_tokens(content), estimated=True)

    @staticmethod
    def _answer(script: dict | None, tool_msgs: list[dict], level: str = "normal") -> str:
        fields: dict = {}
        sources: list[dict] = []
        for m in tool_msgs:
            data = json.loads(guard.unwrap(m["content"]))
            if "error" in data and isinstance(data["error"], dict):
                fields["error"] = data["error"]["message"]
            elif "sources" in data:
                sources += data["sources"]
            elif "verdict" in data and "reason" in data:  # check_affected, one CVE (A15)
                fields["affected"] = _verdict_line(data)
            elif "counts" in data:  # check_affected, one product
                fields["affected"] = _verdict_counts(data)
            elif "watch_status" in data:
                fields["cve"] = _cve_card(data)
            elif data.get("kind") in ("cwe", "atlas_technique"):
                fields["weakness"] = _weakness(data)
            elif "watchlist" in data:
                fields["watch"] = data["message"] + " Watching: " + ", ".join(data["watchlist"]) + "."

        if script is None:
            parts = [fields[k] for k in ("error", "cve", "affected", "weakness") if k in fields]
            if sources:
                head = "How to prevent this kind of bug:" if "cve" in fields else "From the knowledge base:"
                parts.append(f"{head}\n\n{_bullets(sources, 3 if 'cve' in fields else 2)}")
            return "\n\n".join(parts) or NOTHING_FOUND
        limit = script.get("limit", 3)
        fields["sources"] = _bullets(sources, limit)
        fields["cites"] = " ".join(f"[{s['n']}]" for s in sources[:limit])
        template = script["answers"][level] if "answers" in script else script["answer"]
        try:
            return template.format(**fields)
        except KeyError:
            return f"Sorry, a tool didn't give me what I needed: {fields.get('error', 'no result')}"
