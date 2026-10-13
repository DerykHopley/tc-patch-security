from app.rag.chunking import CVE_MAX_CHARS, MAX_CHARS, build_chunks, chunk_cve, chunk_owasp, sections

PAGE = """## LLM99:2025 Example Risk

### Description

First paragraph.

#### A sub heading

Detail under the sub heading.

### Prevention and Mitigation Strategies

Use [least privilege](https://example.org/lp).

### Reference Links

1. [A link](https://example.org)
"""


def test_r1_owasp_split_on_headings():
    names = [n for n, _ in sections(PAGE)]
    assert names == [None, "Description", "Prevention and Mitigation Strategies", "Reference Links"]


def test_r1_subheadings_stay_in_their_section():
    chunks = chunk_owasp("LLM99", "owasp_llm", "LLM99 Example", "https://x", PAGE)
    desc = [c for c in chunks if c.section == "Description"]
    assert "Detail under the sub heading" in " ".join(c.text for c in desc)


def test_r1_references_skipped_and_links_flattened():
    chunks = chunk_owasp("LLM99", "owasp_llm", "LLM99 Example", "https://x", PAGE)
    assert all(c.section != "Reference Links" for c in chunks)
    prevention = next(c for c in chunks if c.section == "Prevention and Mitigation Strategies")
    assert prevention.text == "Use least privilege."


def test_r1_chunk_ids_and_size(shared):
    k, index = shared
    for c in index.chunks:
        assert len(c.text) <= (CVE_MAX_CHARS if c.doc_type == "cve" else MAX_CHARS)
        assert c.chunk_id.startswith(c.doc_id + "#")
    llm01 = [c for c in index.chunks if c.doc_id == "LLM01"]
    assert llm01 and all(c.doc_type == "owasp_llm" and c.title.startswith("LLM01:2025") for c in llm01)
    assert {c.section for c in llm01} >= {"Description", "Prevention and Mitigation Strategies"}


def test_r1_noise_sections_skipped(shared):
    _, index = shared
    skipped = {"List of Mapped CWEs", "Score table", "References", "Reference Links"}
    assert not [c for c in index.chunks if c.section in skipped]


def test_r2_one_doc_per_cve_with_header_and_metadata(shared):
    k, _ = shared
    cve = k.cves.get("CVE-2024-8309")
    chunks = chunk_cve(cve, "LangChain")
    assert chunks[0].text.startswith("CVE-2024-8309 · LangChain · CRITICAL. A vulnerability")
    c = chunks[0]
    assert (c.doc_type, c.product, c.severity, c.cvss, c.owasp, c.kev) == ("cve", "langchain", "CRITICAL", 9.8, "A05", False)
    assert "CWE-89" in c.cwes


def test_r2_long_cve_never_leaves_header_alone(shared):
    k, index = shared
    for c in index.chunks:
        if c.doc_type == "cve":
            assert len(c.text) > len(c.doc_id) + 30, c.chunk_id


def test_r2_every_source_is_chunked(shared):
    k, index = shared
    docs = {c.doc_id for c in index.chunks}
    assert {f"LLM{i:02d}" for i in range(1, 11)} <= docs
    assert {f"A{i:02d}" for i in range(1, 11)} <= docs
    assert {"AML.T0051", "AML.M0015", "AML.CS0000"} <= docs
    assert len([d for d in docs if d.startswith("CVE-")]) == len(k.cves.all())
