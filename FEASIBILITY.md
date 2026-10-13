# Feasibility check: a cybersecurity knowledge base

Can the course chatbot use public security data? Two options compared:

- **General:** OWASP Top 10 (web apps) + CISA KEV + NVD CVEs.
- **LLM-specific:** OWASP Top 10 for LLM apps + MITRE ATLAS + NVD CVEs in AI/LLM software.

Written 2026-10-13. **Decision (2026-10-13): LLM-specific, as recommended below. English only.** All figures checked by running `feasibility/fetch.py` and `feasibility/analyse.py` on that day, unless marked otherwise. Raw numbers: `feasibility/data/summary.json` (the data folder is about 30 MB and is not for committing).

## Short answer

- **Both work.** Every source downloaded without a key, is openly licensed, and has the metadata self-query needs.
- **The LLM-specific option is smaller and more focused:** about 3,500 chunks against about 40,000 or more.
- **It still needs the web Top 10.** 75% of AI-software CVEs with a CWE are ordinary web bugs (code injection, SSRF, path traversal), and they map to the *web* Top 10, not the LLM one.
- **Suggestion:** LLM-specific, with the web Top 10 included as the bridge to CVEs. See "Recommendation".

## The sources

| Source | Licence | Size | Updates | Checked |
| --- | --- | --- | --- | --- |
| OWASP Top 10 2025 (web) | CC BY-SA 4.0 | 10 pages, 12,288 words, ~220 chunks | Every few years | Yes |
| OWASP Top 10 2021 (web) | CC BY-SA 4.0 | 10 pages, ~179 chunks | Superseded | Yes |
| OWASP Top 10 for LLM apps 2025 | CC BY-SA 4.0 | 10 pages, 11,249 words, ~267 chunks | Yearly-ish | Yes |
| MITRE ATLAS 5.6.0 | Apache 2.0 | 16 tactics, 170 techniques, 35 mitigations, 57 case studies, ~718 chunks | Monthly | Yes |
| CISA KEV | Public (US government) | 1,739 exploited CVEs, catalogue 2026.10.08 | Several times a week | Yes |
| NVD CVE API 2.0 | Public (US government) | 38,865 CVEs published in the last 90 days alone | Daily | Yes |

- Chunks are estimates: split on headings, then 600 characters, like the prototype's chunker.
- German translations exist for both OWASP lists (checked), but translations are out of scope (decided 2026-10-13).
- NVD without a key: about 5 requests per 30 s, 2,000 CVEs per request. Full download of the AI keywords took about 5 minutes.

## How the sources link

```text
GENERAL
OWASP web Top 10 ──"List of Mapped CWEs"──► CWE ◄──weakness── NVD CVE ──cveID── KEV (exploited)

LLM-SPECIFIC
OWASP LLM Top 10 ──"Related Frameworks"──► ATLAS technique (AML.T0051 …) ──► mitigations, case studies
AI-software CVE ──CWE──► OWASP web Top 10   (the bridge)
```

- **Web Top 10 → CWE is clean.** 249 CWEs in 2025, and each belongs to exactly one category. So `owasp_category_for_cwe()` is a plain lookup with no ambiguity.
- **2021 vs 2025:** 196 and 249 CWEs, 164 in both. "What changed in 2025?" is a real decomposition test.
- **LLM Top 10 → ATLAS:** the pages cite 14 ATLAS technique IDs, and all 14 exist in ATLAS 5.6.0. But 3 pages cite none (LLM05 Improper Output Handling, LLM06 Excessive Agency, LLM08 Vector and Embedding Weaknesses).
- **LLM Top 10 → CWE is nearly empty.** Only LLM10 mentions one (CWE-400). So there is no direct join from the LLM list to CVEs.
- ATLAS mentions only 5 CVEs, and 34 of its 170 techniques link to ATT&CK.

## Option A: general

**Coverage**

- KEV: 1,739 entries from 2021-11-03 to 2026-10-08. 1,564 have a CWE, and 1,011 of those (65%) map to an OWASP 2025 category.
- KEV fields: vendor, product, date added, due date, known ransomware use (361 "Known"), required action, short description (~200 characters).
- NVD, last 90 days: 33,561 of 38,865 have a CWE, and 25,290 of those (75%) map to OWASP 2025. Top CWEs: XSS (79), improper access control (284), missing authorisation (862), SQL injection (89).
- **Demo question works:** 58 KEV entries added in 2026 have an A05 Injection CWE.

**Problems found**

- **NVD's analysis backlog.** Of the 38,865 recent CVEs only 30% are "Analyzed"; 38% are "Deferred". Only 32% have product data (CPE). A vendor or product filter can't rely on NVD for new CVEs. KEV has vendor and product for every entry.
- **Volume.** About 39,000 CVEs in 90 days. The corpus needs a scope, for example KEV plus the last few months, or a few vendors.
- **A03 Software Supply Chain Failures barely appears** (0 in KEV, 28 in NVD). Its 6 CWEs don't describe how supply-chain attacks are usually filed. Expected, but it means some categories have no CVE examples.
- KEV adds old CVEs too. One added in 2026 is from 2016, so "exploited this year" means `dateAdded`, not the CVE date.

## Option B: LLM-specific

**Coverage**

- ATLAS: 170 techniques (69 sub-techniques), maturity "realized" 64, "demonstrated" 89, "feasible" 17. 57 case studies: 17 real incidents, 40 exercises, dated 2016–2026.
- AI-software CVEs: 2,254 unique over 35 keywords. 1,215 come from LLM apps and tools (LangChain, Ollama, vLLM, Open WebUI, Langflow, Flowise, Dify, LiteLLM, llama.cpp …).
- **Very recent:** 927 of the 1,215 LLM-app CVEs were published in 2026. Good for "what's new" questions and real-time updates.
- Top products: TensorFlow 431, Langflow 173, Open WebUI 144, Flowise 128, vLLM 90.
- 99% have a CWE. 75% map to the *web* Top 10. Top CWEs for LLM apps: code injection (94), SSRF (918), path traversal (22), IDOR (639).
- Real prompt-injection CVEs exist, for example CVE-2023-29374: LangChain's LLMMathChain ran injected code through Python's `exec`.

**Problems found**

- **Only 10 AI CVEs are in KEV** (for example CVE-2025-3248). The "actively exploited" angle is thin here.
- **Keyword search is noisy.** Without exact matching, "prompt injection" also matched SQL injection CVEs that contain the word "prompt". Use `keywordExactMatch` or filter on known products. TensorFlow (431) is classic ML, not LLM; keep or drop on purpose.
- ATLAS is less familiar than OWASP and the questions about it are harder to write.

## Against the brief

| Brief item | General | LLM-specific |
| --- | --- | --- |
| Focused knowledge base | Broad; needs a scope | **Focused** |
| Structured retrieval | **Rich fields** (KEV vendor/product, severity, CWE, dates, ransomware) | Good (severity, CWE, product, date, ATLAS tactic and maturity) |
| Query translation demo | Exploited + category + date questions | LLM risk → ATLAS technique → CVEs questions |
| 3+ tools | CVE lookup, KEV check, CWE → category | The same, plus ATLAS technique lookup |
| Domain security measures | Defend, don't write exploits | The same, and prompt injection is part of the subject |
| Hybrid search (hard) | CVE IDs and product names favour keywords | The same |
| Real-time / automated updates | KEV and NVD feeds | NVD keyword feed, ATLAS monthly |
| Size and cost | ~40,000+ chunks | ~3,500 chunks |

## Recommendation

LLM-specific, with the web Top 10 included:

- OWASP LLM Top 10: the "what and how to prevent" layer for LLM risks.
- MITRE ATLAS: attack techniques, mitigations, real incidents.
- OWASP web Top 10 2025: the bridge, because most AI-software CVEs are web bugs.
- NVD CVEs for a fixed list of LLM products, plus the 10 KEV matches.

That gives about 3,500 chunks (267 + 718 + 220 + ~2,250 CVEs, one chunk each), every source linked to another, and a story that fits the brief: a security assistant for people building LLM apps.

A good demo question: "Which vulnerabilities in LLM app builders this year let an attacker run code, and how should I defend against that?" It uses a product and date filter, the CWE → A05 lookup, LLM05/LLM06 for the advice, and ATLAS for the technique.

## Not checked yet

- How well embeddings separate ATLAS techniques that sound alike. Needs a small retrieval test.
- Whether OWASP's Markdown has noise that hurts chunks (image tags, score tables). The headings look clean.
- Embedding cost for ~3,500 chunks. Small, but not worked out.
- A ready-made test set for this corpus. CyberMetric is about other documents. Questions with exact answers can be built from the structured fields (severity, CWE, KEV status) with no LLM judge.
