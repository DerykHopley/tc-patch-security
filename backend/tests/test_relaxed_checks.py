"""Three expectations relaxed after the A20 runs (#54): they failed good answers. Check ids: F54.n.

The checks are pure functions of `expect` and a ChatReply, so they're tested on hand-built replies; the questions'
own `expect` comes from fixtures/fake_script.json, as a run reads it.
"""
from app.evals.checks import failure_kind, score, score_levels
from app.evals.model_check import questions
from app.schemas import ChatReply, Source, ToolCallRecord, Usage


def src(n: int) -> Source:
    return Source(n=n, chunk_id=f"c{n}", doc_id=f"d{n}", doc_type="cve", title=f"T{n}", url="u", snippet="s")


def call(name: str, result: dict | None = None) -> ToolCallRecord:
    return ToolCallRecord(id="1", name=name, args={}, status="ok", result=result or {}, duration_ms=1.0)


def reply(answer: str, tools=(), sources=(1,)) -> ChatReply:
    return ChatReply(answer=answer, sources=[src(n) for n in sources], tool_calls=list(tools), query=None,
                     usage=Usage(), steps=1)


def by_name(checks) -> dict:
    return {c.name: c for c in checks}


def expect_of(qid: str) -> dict:
    return next(q["expect"] for q in questions() if q["id"] == qid)


# --- F54.1: "Right tools" can accept one of several tools --------------------------------------------------------

def test_f54_1_tools_any_passes_with_either_tool_and_fails_with_neither():
    expect = {"tools_any": ["check_affected", "lookup_cve"]}
    assert by_name(score(expect, reply("x", [call("lookup_cve")])))["tools"].passed
    assert by_name(score(expect, reply("x", [call("check_affected")])))["tools"].passed
    miss = by_name(score(expect, reply("x", [call("search_security")])))["tools"]
    assert not miss.passed
    assert miss.expected == "check_affected or lookup_cve" and miss.got == "search_security"


# --- F54.2: Q-affected accepts lookup_cve, and its key fact is the product, not the CVE id the question names ------

LUNA = ("Yes. Your watched Langflow version is **1.2.0**, which is affected; the fixed version is **1.3.0**. The "
        "vulnerability can let a remote, unauthenticated attacker execute code. [1]")  # GPT-6 Luna, A20 run


def test_f54_2_q_affected_passes_a_right_verdict_from_lookup_cve_without_the_cve_id():
    verdict = call("lookup_cve", {"id": "CVE-2025-3248", "verdict": "affected", "fixed_version": "1.3.0"})
    got = by_name(score(expect_of("Q-affected"), reply(LUNA, [verdict])))
    assert all(c.passed for c in got.values()), [c for c in got.values() if not c.passed]
    assert {"tools", "key_fact", "verdict"} <= set(got)


def test_f54_2_q_affected_still_fails_an_answer_that_never_names_the_product():
    verdict = call("check_affected", {"verdict": "affected", "fixed_version": "1.3.0"})
    vague = "Yes, CVE-2025-3248 affects you. Upgrade to 1.3.0. [1]"
    assert not by_name(score(expect_of("Q-affected"), reply(vague, [verdict])))["key_fact"].passed


# --- F54.3: Q12 asks for "LLM01" at normal and deep dive only: the simple level leaves codes out on purpose ---------

SIMPLE = "Prompt injection is when bad text tricks the bot into doing what it says [1]."
NORMAL = "Prompt injection (OWASP LLM01) is input that changes the model's behaviour [1]."
DEEP = "Prompt injection, OWASP LLM01:2025, exploits the lack of separation between instructions and data [1]."


def levels_of(simple: str, normal: str, deep: str) -> dict:
    return by_name(score_levels(expect_of("Q12"), {"simple": reply(simple, [call("search_security")]),
                                                    "normal": reply(normal, [call("search_security")]),
                                                    "deep_dive": reply(deep, [call("search_security")])}))


def test_f54_3_q12_passes_a_simple_answer_without_the_code():
    fact = levels_of(SIMPLE, NORMAL, DEEP)["key_fact"]
    assert fact.passed and fact.expected == "one of: LLM01 (at normal, deep dive)"


def test_f54_3_q12_still_fails_a_deep_dive_without_the_code_and_names_the_level():
    fact = levels_of(SIMPLE, NORMAL, DEEP.replace("OWASP LLM01:2025, ", ""))["key_fact"]
    assert not fact.passed and fact.got.startswith("deep dive: ") and "simple" not in fact.got


def test_f54_3_the_other_checks_still_run_at_every_level():
    got = levels_of(SIMPLE, NORMAL, DEEP)
    assert got["cites"].expected.endswith("(at every level)") and got["tools"].passed


# --- F54.4: the report's kind of miss reads only the levels the key fact is asked at ------------------------------

def test_f54_4_key_fact_missing_at_one_of_its_levels_is_a_levels_miss_and_at_both_an_answer_miss():
    miss = {"name": "key_fact", "expected": "one of: LLM01 (at normal, deep dive)"}
    one = {"simple": {"answer": SIMPLE}, "normal": {"answer": NORMAL}, "deep_dive": {"answer": "No code here."}}
    assert failure_kind(miss, one) == "levels"
    both = {"simple": {"answer": "It is LLM01."}, "normal": {"answer": "No code."}, "deep_dive": {"answer": "None."}}
    assert failure_kind(miss, both) == "answer"  # the simple level isn't asked: its LLM01 doesn't count


# --- F54.5: the report says which expectations changed, and which runs were scored on the old ones -----------------

def test_f54_5_the_grid_marks_a_changed_expectation_and_a_run_scored_before_it(deps):
    import re

    from app.evals import model_check, report
    from app.evals.runs import RunStore

    new = model_check.start(deps, ids=["Q-affected", "Q12", "Q1"], wait=True)
    store = RunStore.for_settings(deps.settings)
    old = new | {"id": "20261015-100000-000-0001", "model": "Local · old-model",
                 "started": "2026-10-15T10:00:00+00:00"}  # an A20 run, scored before the change
    store.save(model_check.KIND, old)
    html = report.from_store(store, as_of=deps.settings.as_of, model_ids=[new["id"], old["id"]])
    grid = re.search(r'<section id="grid".*?</section>', html, re.S).group(0)

    def row(qid):
        return re.search(rf'<tr><th scope="row">{qid} .*?</tr>', grid, re.S).group(0)

    for qid in ("Q-affected", "Q12"):
        assert "expectation changed 2026-10-16" in row(qid), qid
        cells = re.findall(r"<td.*?</td>", row(qid), re.S)
        assert "old expectation" not in cells[0] and "old expectation" in cells[1]  # the new run, then the old
    assert "expectation changed" not in row("Q1")
    # What changed, in words, under the grid: the old and the new expectation, and why
    for words in ("check_affected or lookup_cve", "CVE-2025-3248", "Langflow", "LLM01", "normal and deep dive",
                  "#54"):
        assert words in grid, words
