"""The snapshot loader (moved from proto, where it was only tested through the tools). Check ids: A01.n."""


def test_a01_5_snapshot_loads_with_its_as_of_date(knowledge):
    assert knowledge.manifest["as_of"] == "2026-10-13"
    assert len(knowledge.products) == 12
    assert len(knowledge.cves.all()) == 929
    assert len(knowledge.cves.kev) == 9


def test_a01_5_cve_lookup_ignores_case(knowledge):
    assert knowledge.cves.get("cve-2024-8309")["product"] == "langchain"
    assert knowledge.cves.get("CVE-1999-0001") is None


def test_a01_5_product_names_resolve_with_aliases(knowledge):
    assert knowledge.resolve_product("Open WebUI") == "open-webui"
    assert knowledge.resolve_product("openwebui") == "open-webui"
    assert knowledge.resolve_product("Notion") is None
    assert knowledge.resolve_product("") is None


def test_a01_5_owasp_category_by_code(knowledge):
    assert knowledge.category("LLM01")["title"]
    assert knowledge.category("LLM99") is None
    assert knowledge.category(None) is None
