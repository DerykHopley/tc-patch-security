"""The snapshot build (scripts/build_fixtures.py), moved from proto. Check ids: A14.n, from ticket #16.

No test calls the network: the build reads the committed raw downloads (snapshot_raw/), and the
fetch step is tested with fake OSV and EPSS servers.
"""
import json

import pytest

from app.config import FIXTURES, ROOT
from scripts import build_fixtures as build

EXISTING = ["cves.json", "kev.json", "owasp.json", "atlas.json",
            *(f"owasp_llm/LLM{n:02d}.md" for n in range(1, 11)),
            *(f"owasp_web/A{n:02d}.md" for n in range(1, 11))]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("fixtures")
    build.build(ROOT / "snapshot_raw", out)
    return out


@pytest.mark.parametrize("name", EXISTING)
def test_a14_1_existing_sources_build_byte_identical(built, name):
    assert (built / name).read_bytes() == (FIXTURES / name).read_bytes()
