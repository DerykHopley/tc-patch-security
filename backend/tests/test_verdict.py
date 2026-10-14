"""The verdict (seam 2): a pure function, table-driven. Check ids: A15.n, from ticket #17.

Each row: the product's OSV coverage, the CVE's OSV entries for that product, your usage and version, and the
verdict, reason and fixed version expected. Expected values are written by hand from OSV's range rules
(introduced <= v < fixed, or v <= last_affected) and each ecosystem's version order.
"""
import pytest

from app.verdict import verdict


def entry(ecosystem, package, *ranges):
    """One OSV entry: ranges as (introduced, fixed, last_affected)."""
    rs = [{"introduced": i, "fixed": f, "last_affected": la} for i, f, la in ranges]
    return {"ecosystem": ecosystem, "package": package, "ranges": rs, "fixed": [r["fixed"] for r in rs if r["fixed"]]}


LANGFLOW = [entry("PyPI", "langflow", ("0", "1.3.0", None))]  # CVE-2025-3248
GRADIO = [entry("PyPI", "gradio", ("0", "1.9.0", None))]
FLOWISE = [entry("npm", "flowise", ("0", "3.1.0", None)), entry("npm", "flowise-components", ("0", "3.1.0", None))]
FLOWISE_PATCH = [entry("npm", "flowise", ("0", "2.2.7", None))]
OLLAMA = [entry("Go", "github.com/ollama/ollama", ("0", "0.1.29", None))]  # CVE-2024-28224
OLLAMA_LAST = [entry("Go", "github.com/ollama/ollama", ("0", None, "0.3.14"))]  # CVE-2024-12055: no fix listed
CORE_TWO_LINES = [entry("PyPI", "langchain-core", ("1.0.0", "1.0.7", None), ("0", "0.3.80", None))]  # CVE-2025-65106
COMMUNITY_LATER = [entry("PyPI", "langchain-community", ("0.2.0", "0.2.19", None))]  # CVE-2024-8309
NO_FIX_YET = [entry("PyPI", "vllm", ("0.5.0", None, None))]

TABLE = [
    # case, coverage, entries, your version, verdict, reason, fixed version
    # PEP 440 (PyPI)
    ("before the fix", "package", LANGFLOW, "1.2.0",
     "affected", "1.2.0 is before the fixed version 1.3.0 (langflow)", "1.3.0"),
    ("exactly the fixed version", "package", LANGFLOW, "1.3.0",
     "not_affected", "1.3.0 is at or after the fixed version 1.3.0 (langflow)", "1.3.0"),
    ("after the fix", "package", LANGFLOW, "1.4.2",
     "not_affected", "1.4.2 is at or after the fixed version 1.3.0 (langflow)", "1.3.0"),
    ("release candidate of the fix", "package", LANGFLOW, "1.3.0rc1",
     "affected", "1.3.0rc1 is before the fixed version 1.3.0 (langflow)", "1.3.0"),
    ("dev release of the fix", "package", LANGFLOW, "1.3.0.dev2",
     "affected", "1.3.0.dev2 is before the fixed version 1.3.0 (langflow)", "1.3.0"),
    ("post release of the fix", "package", LANGFLOW, "1.3.0.post1",
     "not_affected", "1.3.0.post1 is at or after the fixed version 1.3.0 (langflow)", "1.3.0"),
    ("PEP 440 compares numbers, not text", "package", GRADIO, "1.10.0",
     "not_affected", "1.10.0 is at or after the fixed version 1.9.0 (gradio)", "1.9.0"),
    ("two fixed lines: old line, before", "package", CORE_TWO_LINES, "0.3.79",
     "affected", "0.3.79 is before the fixed version 0.3.80 (langchain-core)", "0.3.80"),
    ("two fixed lines: old line, fixed", "package", CORE_TWO_LINES, "0.3.80",
     "not_affected", "0.3.80 is at or after the fixed version 0.3.80 (langchain-core)", "0.3.80"),
    ("two fixed lines: new line, before", "package", CORE_TWO_LINES, "1.0.6",
     "affected", "1.0.6 is before the fixed version 1.0.7 (langchain-core)", "1.0.7"),
    ("two fixed lines: new line, fixed", "package", CORE_TWO_LINES, "1.0.7",
     "not_affected", "1.0.7 is at or after the fixed version 1.0.7 (langchain-core)", "1.0.7"),
    ("two fixed lines: pre-release before the new line", "package", CORE_TWO_LINES, "1.0.0a1",
     "not_affected", "1.0.0a1 is at or after the fixed version 0.3.80 (langchain-core)", "0.3.80"),
    ("before the first affected version", "package", COMMUNITY_LATER, "0.1.20",
     "not_affected", "0.1.20 is outside the affected versions (langchain-community)", None),
    ("affected range with no fix yet", "package", NO_FIX_YET, "0.6.1",
     "affected", "0.6.1 is in an affected range with no fix yet (vllm)", None),
    # SemVer (npm)
    ("npm: before the fix, in both packages", "package", FLOWISE, "3.0.13",
     "affected", "3.0.13 is before the fixed version 3.1.0 (flowise)", "3.1.0"),
    ("npm: pre-release of the fix", "package", FLOWISE, "3.1.0-beta.1",
     "affected", "3.1.0-beta.1 is before the fixed version 3.1.0 (flowise)", "3.1.0"),
    ("npm: exactly the fixed version", "package", FLOWISE, "3.1.0",
     "not_affected", "3.1.0 is at or after the fixed version 3.1.0 (flowise)", "3.1.0"),
    ("npm: semver compares numbers, not text", "package", FLOWISE, "3.10.0",
     "not_affected", "3.10.0 is at or after the fixed version 3.1.0 (flowise)", "3.1.0"),
    ("npm: a pre-release tag sorts before its release", "package", FLOWISE_PATCH, "2.2.7-patch.1",
     "affected", "2.2.7-patch.1 is before the fixed version 2.2.7 (flowise)", "2.2.7"),
    # Go module versions
    ("Go: with the v prefix, before the fix", "package", OLLAMA, "v0.1.28",
     "affected", "v0.1.28 is before the fixed version 0.1.29 (github.com/ollama/ollama)", "0.1.29"),
    ("Go: with the v prefix, exactly the fix", "package", OLLAMA, "v0.1.29",
     "not_affected", "v0.1.29 is at or after the fixed version 0.1.29 (github.com/ollama/ollama)", "0.1.29"),
    ("Go: release candidate of the fix", "package", OLLAMA, "0.1.29-rc0",
     "affected", "0.1.29-rc0 is before the fixed version 0.1.29 (github.com/ollama/ollama)", "0.1.29"),
    ("Go: last affected version, at it", "package", OLLAMA_LAST, "0.3.14",
     "affected", "0.3.14 is at or before the last affected version 0.3.14 (github.com/ollama/ollama); "
     "no fixed version listed", None),
    ("Go: last affected version, after it", "package", OLLAMA_LAST, "0.3.15",
     "not_affected", "0.3.15 is outside the affected versions (github.com/ollama/ollama)", None),
    # unknown, with the reason
    ("missing version", "package", LANGFLOW, None, "unknown", "no version given", "1.3.0"),
    ("blank version", "package", CORE_TWO_LINES, "  ", "unknown", "no version given", "1.0.7"),
    ("Dify: no package data", "none", [], "1.4.0", "unknown", "no version data for this product", None),
    ("llama.cpp: commit ranges only", "commits", [], "b4500", "unknown", "only code commits", None),
    ("covered product, CVE not in OSV", "package", [], "1.2.0", "unknown", "no version data for this CVE", None),
    ("a version we can't read", "package", LANGFLOW, "latest",
     "unknown", "version not understood: 'latest' isn't a PyPI (PEP 440) version", "1.3.0"),
]


@pytest.mark.parametrize("case,coverage,entries,version,want,reason,fixed", TABLE, ids=[r[0] for r in TABLE])
def test_a15_2_verdict_table(case, coverage, entries, version, want, reason, fixed):
    v = verdict(coverage, entries, "self_hosted", version)
    assert (v.verdict, v.reason, v.fixed_version) == (want, reason, fixed)


@pytest.mark.parametrize("usage,who", [("self_hosted", "you"), ("library", "you"),
                                       ("transitive", "upstream"), ("hosted", "vendor")])
def test_a15_3_who_acts_from_usage(usage, who):
    for coverage, entries, version in (("package", LANGFLOW, "1.2.0"), ("none", [], None)):
        assert verdict(coverage, entries, usage, version).who_acts == who


def test_a15_2_every_snapshot_version_parses_in_its_ecosystem(knowledge):
    """The ecosystem rules read every version OSV gives in the snapshot (pre-releases included)."""
    from app.verdict import parse_version

    for entries in knowledge.osv["cves"].values():
        for e in entries:
            for r in e["ranges"]:
                for v in (r["introduced"], r["fixed"], r["last_affected"]):
                    if v and v != "0":
                        parse_version(e["ecosystem"], v)


# --- A16b.2: "no fix yet": OSV lists the CVE for the product's packages, but no fixed version -------------------

def _e(*ranges):
    return {"ecosystem": "PyPI", "package": "p", "fixed": [f for _, f, _ in ranges if f],
            "ranges": [{"introduced": i, "fixed": f, "last_affected": la} for i, f, la in ranges]}


@pytest.mark.parametrize("coverage,entries,want", [
    ("package", [_e(("0", None, None))], True),  # an open range
    ("package", [_e(("0", None, "1.2"))], True),  # last affected only
    ("package", [_e(("0", "1.3", None))], False),  # a fix exists
    ("package", [_e(("0", None, None)), _e(("0", "2.0", None))], False),  # one package has a fix
    ("package", [], False),  # no OSV record for this CVE: unknown, not "no fix"
    ("commits", [_e(("0", None, None))], False),  # commit ranges only: unknown
    ("none", [], False),
])
def test_a16b_2_no_fix_table(coverage, entries, want):
    from app.verdict import no_fix

    assert no_fix(coverage, entries) is want
