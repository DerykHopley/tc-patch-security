"""Download the raw data for the feasibility check into feasibility/data/.

Run: python3 -I feasibility/fetch.py
Stdlib only. NVD without an API key allows about 5 requests per 30 s, so NVD calls sleep 6.5 s.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
UA = {"User-Agent": "tc-sprint2-feasibility/0.1"}

OWASP_RAW = "https://raw.githubusercontent.com/OWASP/Top10/master"
OWASP_2025 = [
    "A01_2025-Broken_Access_Control", "A02_2025-Security_Misconfiguration",
    "A03_2025-Software_Supply_Chain_Failures", "A04_2025-Cryptographic_Failures",
    "A05_2025-Injection", "A06_2025-Insecure_Design", "A07_2025-Authentication_Failures",
    "A08_2025-Software_or_Data_Integrity_Failures",
    "A09_2025-Security_Logging_and_Alerting_Failures",
    "A10_2025-Mishandling_of_Exceptional_Conditions",
]
OWASP_2021 = [
    "A01_2021-Broken_Access_Control", "A02_2021-Cryptographic_Failures", "A03_2021-Injection",
    "A04_2021-Insecure_Design", "A05_2021-Security_Misconfiguration",
    "A06_2021-Vulnerable_and_Outdated_Components",
    "A07_2021-Identification_and_Authentication_Failures",
    "A08_2021-Software_and_Data_Integrity_Failures",
    "A09_2021-Security_Logging_and_Monitoring_Failures",
    "A10_2021-Server-Side_Request_Forgery_(SSRF)",
]
LLM_RAW = "https://raw.githubusercontent.com/OWASP/www-project-top-10-for-large-language-model-applications/main/2_0_vulns"
LLM_FILES = [
    "LLM01_PromptInjection", "LLM02_SensitiveInformationDisclosure", "LLM03_SupplyChain",
    "LLM04_DataModelPoisoning", "LLM05_ImproperOutputHandling", "LLM06_ExcessiveAgency",
    "LLM07_SystemPromptLeakage", "LLM08_VectorAndEmbeddingWeaknesses", "LLM09_Misinformation",
    "LLM10_UnboundedConsumption",
]
ATLAS_URL = "https://raw.githubusercontent.com/mitre-atlas/atlas-data/main/dist/ATLAS.yaml"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"

# AI/LLM software to look for in NVD descriptions. Multi-word keywords must all appear.
AI_KEYWORDS = [
    "langchain", "llama_index", "llamaindex", "ollama", "vllm", "huggingface transformers",
    "pytorch", "tensorflow", "keras", "gradio", "mlflow", "anyscale ray", "onnx",
    "triton inference server", "open webui", "lollms", "anything-llm", "h2o", "kubeflow",
    "comfyui", "localai", "text-generation-webui", "langflow", "dify", "flowise", "litellm",
    "llama.cpp", "haystack", "chromadb", "milvus", "qdrant", "weaviate", "large language model",
    "llm", "prompt injection",
]


def get(url: str, retries: int = 3) -> bytes:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - report and retry
            print(f"  retry {attempt + 1} for {url[:90]}: {e}", file=sys.stderr)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"failed: {url}")


def save(name: str, body: bytes) -> None:
    path = DATA / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def compact(v: dict) -> dict:
    """Keep only the NVD fields the check needs."""
    c = v["cve"]
    desc = next((d["value"] for d in c.get("descriptions", []) if d["lang"] == "en"), "")
    cwes = sorted({d["value"] for w in c.get("weaknesses", []) for d in w["description"]
                   if d["value"].startswith("CWE-")})
    score = severity = None
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30"):
        if c.get("metrics", {}).get(key):
            data = c["metrics"][key][0]["cvssData"]
            score, severity = data.get("baseScore"), data.get("baseSeverity")
            break
    cpes = sorted({m["criteria"].split(":")[3] + ":" + m["criteria"].split(":")[4]
                   for cfg in c.get("configurations", []) for n in cfg["nodes"]
                   for m in n["cpeMatch"]})
    return {"id": c["id"], "published": c["published"], "status": c.get("vulnStatus"),
            "description": desc, "cwes": cwes, "score": score, "severity": severity,
            "vendor_products": cpes[:20]}


def nvd(params: dict) -> list[dict]:
    """All pages for one query, compacted."""
    out, start = [], 0
    while True:
        q = urllib.parse.urlencode({**params, "resultsPerPage": 2000, "startIndex": start})
        time.sleep(6.5)
        page = json.loads(get(f"{NVD}?{q}"))
        out += [compact(v) for v in page["vulnerabilities"]]
        start += page["resultsPerPage"]
        if start >= page["totalResults"]:
            return out


def main() -> None:
    DATA.mkdir(exist_ok=True)
    if sys.argv[1:] == ["ai"]:  # rerun only the AI keyword part
        return fetch_ai()
    print("OWASP Top 10 2025/2021 (en + de) and LLM Top 10 2025 (en + de-DE)")
    for year, names in (("2025", OWASP_2025), ("2021", OWASP_2021)):
        for n in names:
            for lang in ("en", "de"):
                try:
                    save(f"owasp/{year}/{lang}/{n}.md",
                         get(f"{OWASP_RAW}/{year}/docs/{lang}/{urllib.parse.quote(n)}.md", retries=1))
                except RuntimeError:
                    print(f"  missing {year}/{lang}/{n}")
    for n in LLM_FILES:
        save(f"owasp_llm/en/{n}.md", get(f"{LLM_RAW}/{n}.md"))
        try:
            save(f"owasp_llm/de/{n}.md", get(f"{LLM_RAW}/translations/de-DE/{n}.md", retries=1))
        except RuntimeError:
            print(f"  missing llm de/{n}")

    print("MITRE ATLAS and CISA KEV")
    save("ATLAS.yaml", get(ATLAS_URL))
    save("kev.json", get(KEV_URL))

    print("NVD: CVEs published in the last 90 days (general sample)")
    end = datetime.now(timezone.utc).replace(microsecond=0)
    begin = end - timedelta(days=90)
    fmt = "%Y-%m-%dT%H:%M:%S.000Z"
    recent = nvd({"pubStartDate": begin.strftime(fmt), "pubEndDate": end.strftime(fmt)})
    save("nvd_recent90.json", json.dumps(recent).encode())
    print(f"  {len(recent)} CVEs")

    fetch_ai()


def fetch_ai() -> None:
    print("NVD: AI/LLM software keywords", flush=True)
    ai: dict[str, dict] = {}
    hits: dict[str, int] = {}
    for kw in AI_KEYWORDS:
        rows = nvd({"keywordSearch": kw})
        hits[kw] = len(rows)
        for r in rows:
            entry = ai.setdefault(r["id"], {**r, "keywords": []})
            entry["keywords"] = sorted({*entry["keywords"], kw})
        print(f"  {kw}: {len(rows)}", flush=True)
    save("nvd_ai.json", json.dumps({"hits": hits, "cves": list(ai.values())}).encode())
    print(f"  {len(ai)} unique AI CVEs")


if __name__ == "__main__":
    main()
