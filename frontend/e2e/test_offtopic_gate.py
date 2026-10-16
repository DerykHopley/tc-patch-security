"""Browser check (seam 3) for the off-topic gate (#53) in the Dev page's search playground. Check ids: F53.<n>."""
from playwright.sync_api import expect
from test_dev import dev_page, run_search  # noqa: F401 (dev_page is a fixture)

# BM25 matches "learning"; for the hash embedder the made-up words keep every vector hit below its threshold.
GATED = "learning zzqa zzqb zzqc zzqd zzqe zzqf zzqg"


def test_f53_5_playground_shows_the_gate(dev_page):
    page = dev_page()
    run_search(page, GATED)
    plan = page.locator(".play-plan")
    expect(plan).to_contain_text("off-topic: keyword hits dropped")
    run_search(page, "prompt injection")
    expect(plan).not_to_contain_text("off-topic")
