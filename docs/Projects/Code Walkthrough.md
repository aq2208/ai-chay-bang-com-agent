# Code Walkthrough

#project #architecture #code

> [!info] Canonical design: **[[Projects/00 - Project Home]]**. Updated 2026-06-11 for AgentBase.

## Updated for AgentBase (2026-06-11)

Key deltas since the original walkthrough below:

- **`main.py` is now the AgentBase entrypoint** (`greennode-agentbase` SDK, `@app.entrypoint`,
  `POST /invocations`, port 8080). It exposes `handle_payload(payload)` dispatching on `payload["action"]`:
  `run` (job pipeline) or `query` (agentic Q&A). The old FastAPI + APScheduler server moved to **`local_api.py`** (local dev only).
- **LLM = single `google/gemma-4-31b-it` via MaaS.** `config.py` gained `LLM_BASE_URL`; `llm_client._openai*`
  route through it. Use `LLM_PROVIDER=openai` + `LLM_BASE_URL` for MaaS; `google` (Gemini) stays for Colab dev.
- **RAG-grounded classification.** `knowledge_base/index.py` now also builds a **`taxonomy`** collection from
  `docs/taxonomy.md` and tags solution chunks with their **domain**. `search.py` adds `search_taxonomy()`.
  `processors/classifier.py` retrieves grounding examples before each classify call (falls back to bare-list if the index is missing).
- **Agentic Q&A.** New **`knowledge_base/issues_store.py`** — `index_issues()` (called at the end of each job)
  + `answer_question()` (RAG over the `issues` collection). Wired into both jobs and the `query` action.
- **Real Jira connector** implemented (`connectors/jira.py`, JQL). `config.py` accepts both `FB_PAGE_IDS` and legacy `FB_PAGE_ID`.
- **Bronze crawl layer.** Crawling is decoupled and runs offline: **`crawlers/threads_crawler.py`** (Playwright
  public keyword search → base64 images → MD5 dedup) writes `data/raw/threads_<ts>.jsonl` via
  **`crawlers/bronze.py`** (shared JSONL IO). **`connectors/threads.py` now reads the latest bronze file** and
  normalizes `SocialPost` → `{id, source, text, images, timestamp}`. `processors/image_analyzer.py` handles
  base64 data-URI images. Crawler deps are in `requirements-crawler.txt` (not in the agent image).
- **Packaging:** production `requirements.txt` (slim — `greennode-agentbase`, `openai`, ML, connectors);
  dev extras in `requirements-dev.txt`; `Dockerfile` bakes PhoBERT + MiniLM + the ChromaDB index;
  `.greennode.json.example` + `.env.agentbase.example` templates.

The per-file notes below remain accurate for the pipeline internals.

---

## Entry Points

There is no single `main.py` yet — that comes in Phase 7. Right now you interact with the project through:

| File | What it is |
|------|-----------|
| `test_phase2.py` | Test runner — runs each processor on mock data |
| `.venv/bin/python -c "..."` | Quick one-off tests in the terminal |
| (Phase 7) `main.py` | FastAPI server — `/run/jira`, `/run/social` endpoints |

---

## Project Root Files

### `config.py`
The single source of truth for all settings. Reads from `.env` via `python-dotenv`.

Key exports used everywhere:
- `LLM_PROVIDER` — which API to call (`anthropic` / `google` / `openai`)
- `LLM_API_KEY` — the key for that provider
- `MODEL_FAST` / `MODEL_SMART` — model names, auto-defaulted per provider
- `DOMAINS` / `SEGMENTS` — the classification taxonomy
- `SENTIMENT_THRESHOLD` — confidence cutoff for PhoBERT (default 0.75)
- `GROUPING_THRESHOLD` — cosine similarity to merge duplicate issues (default 0.82)

### `llm_client.py`
A thin wrapper that hides all provider-specific code behind one method:

```python
from llm_client import llm

text = llm.chat(
    system="You are a classifier...",
    user="Visa payment failed",
    max_tokens=10,
    fast=True  # False → uses MODEL_SMART
)
```

**Why it exists:** Every processor used to import `anthropic` directly. Now they all import `llm`. To switch from Claude to Gemini, you change `.env` — no processor code changes.

The Google provider also handles **rate-limit retries** automatically: if the API returns 429, it reads the "retry in Xs" from the error message and sleeps before retrying.

### `mock_data.py`
Fake data for development. Has 5 Jira tickets and 8 social posts (6 negative, 2 positive).

```python
from mock_data import get_mock_jira, get_mock_social
```

Each item is a dict with: `id`, `source`, `text`, `images`, `timestamp`.

---

## `processors/` — Pipeline Stages

Each file is one or two pipeline stages. They are pure functions — they take data in, return data out, no side effects.

### `preprocessor.py` — Stage 1

**No API calls. No models. Pure Python.**

```
clean_text("Zalopay bị lỗi rồi!!! 😡 http://fb.com")
→ "Zalopay bị lỗi rồi"
```

Functions:
- `clean_text(text)` → removes URLs, #hashtags, @mentions, emoji, normalizes spaces
- `is_meaningful(text, min_words=4)` → drops posts under 4 words
- `deduplicate(items)` → removes near-identical posts using first 80 chars as key
- `preprocess(items)` → runs all three in sequence, returns new list (original not mutated)

**Why preprocess before LLM?** Emoji and URLs add noise to sentiment models and waste LLM tokens. Clean once at the start, all downstream stages benefit.

---

### `sentiment.py` — Stage 2 (Social job only)

**Two-step: ML model first, LLM only for borderline cases.**

```python
is_negative("Zalopay bị lỗi rồi")     → True
is_negative("Zalopay tiện lợi lắm")   → False
filter_negative(posts)                 → keeps only negatives
```

Flow inside `is_negative(text)`:
1. PhoBERT model runs → `{"label": "NEG", "score": 0.94}`
2. If score ≥ `SENTIMENT_THRESHOLD` (0.75) → trust the ML result, return immediately
3. If borderline → call LLM: "Is this text a complaint? YES or NO"

**Why PhoBERT?** It's a Vietnamese BERT model — much better than generic multilingual models for Vietnamese social media text. Free, offline, runs on Apple Silicon MPS (fast).

**Why lazy-load?** PhoBERT takes ~2s to load and ~500MB RAM. It's only loaded when `is_negative()` is first called, not at import time. Tests that don't need sentiment won't pay that cost.

---

### `issue_extractor.py` — Stage 4

**One LLM call per post → one clean English sentence.**

```python
extract_issue("Zalopay bị lỗi rồi! Không nạp tiền được bằng Visa suốt 2 tiếng!!")
→ "Visa payment failing for two hours with unspecified error."
```

Why translate to English?
- RAG search works better on normalized English than noisy Vietnamese
- Semantic grouping clusters issues correctly only when phrasing is consistent
- The final report is in English for the Product Owner

`max_tokens=60` — one sentence needs at most ~15 tokens. Low cap saves money and forces conciseness.

---

### `classifier.py` — Stages 5 & 6

**Two LLM calls: domain first, then segment (depends on domain).**

```python
classify_domain("Visa top-up failing with error E5001")  → "Payment"
classify_segment("Visa top-up failing...", "Payment")    → "Top-up"
```

Why two separate calls (not one)?
- Segment options depend on which domain was chosen
- Smaller, focused prompts produce more reliable outputs than one big prompt
- If domain is wrong, you can detect and fix it independently

Both calls use `max_tokens=10` (the answer is at most 2–3 words) and `fast=True` (Haiku/Flash, not the expensive model).

If the model returns something not in the allowed list, it defaults to `"Other"` / `options[0]` — never crashes on unexpected output.

---

## Data Flow Diagram

```
mock_data.py
    │
    ▼
preprocess()          # clean, filter, dedup
    │
    ├─(social)──► filter_negative()    # PhoBERT + LLM
    │
    ▼
[image_analyzer()]    # Phase 4 — not yet built
    │
    ▼
extract_issue()       # LLM → clean English sentence
    │
    ▼
classify_domain()     # LLM → domain
classify_segment()    # LLM → segment
    │
    ├──► [grouper()]          # Phase 4 — embeddings + cosine similarity
    ├──► [kb_search()]        # Phase 3 — RAG
    │
    ▼
[generate_report()]   # Phase 5 — LLM table
[run_guardrails()]    # Phase 5 — validate output
    │
    ▼
output/report.md
```

---

## How to Read the Code Quickly

1. Start with `config.py` — understand all the constants
2. Read `llm_client.py` — understand how LLM calls are made
3. Read `preprocessor.py` — simplest processor, pure Python, no APIs
4. Read `issue_extractor.py` — simplest LLM processor (one call, one output)
5. Read `classifier.py` — shows two-call chaining pattern
6. Read `sentiment.py` — shows hybrid ML+LLM pattern
7. Read `test_phase2.py` — shows how everything fits together

---

## `knowledge_base/` — RAG System (Phase 3) ✅

### `index.py`

Reads all `.md` files from `knowledge_base/docs/`, splits each by `---` separators into issue-level chunks, embeds with `paraphrase-multilingual-MiniLM-L12-v2`, stores in ChromaDB.

Only chunks containing `## Suggested Approach` are indexed — header/metadata blocks are excluded since they have no actionable content.

Run manually whenever docs change:
```bash
.venv/bin/python knowledge_base/index.py
```

### `search.py`

Two public functions:

```python
search(issue, top_k=2)         # returns list of {"text", "filename", "similarity"}
get_suggested_approach(issue)  # returns the Suggested Approach text, or escalation fallback
```

Uses the same `paraphrase-multilingual-MiniLM-L12-v2` model. Filters by `KB_SIMILARITY_THRESHOLD = 0.48`. Both models lazy-load on first call.

**Why 0.48?** The embedding model scores "Visa payment failed" (extractor output) at ~0.50 against the "Visa Top-up Failure" chunk. 0.48 catches this. Unrelated queries score ~0.22, so there's a clear gap.

### `docs/`

5 KB files covering all 5 domains: `payment.md`, `qr_code.md`, `account.md`, `app_performance.md`, `merchant.md`. Each file has multiple issue sections separated by `---`. Each section has a `## Suggested Approach` with numbered resolution steps.

**Team note:** Add more `.md` files to `docs/` as needed and re-run `index.py`. No code changes required.

---

## `processors/image_analyzer.py` — Stage 3 (Social job only) ✅

**One Vision LLM call per post → structured analysis dict.**

```python
samples = load_sample_images()           # call once at job startup
result  = analyze_image(url, samples)    # per post
# result = {"description", "matched_sample", "domain", "confidence"}
```

`load_sample_images()` walks `sample_images/<Domain>/` and base64-encodes all PNGs/JPGs. Returns `[]` if empty — analyzer still works, just returns `domain="Other"`.

`_parse_json()` handles LLM output that wraps JSON in extra text, and provides a safe fallback dict on total parse failure.

**Team note:** Add labeled PNG/JPG files to `sample_images/<Domain>/` to enable domain matching. No code changes needed.

---

## `processors/grouper.py` — Stage 7 ✅

**Greedy cosine clustering to merge near-duplicate issues.**

```python
groups = group_similar(items)
# Each group: {"extracted_issue", "mentions", "sources", "ids", ...}
# Sorted by mentions descending (highest-impact issues first)
```

Uses `paraphrase-multilingual-MiniLM-L12-v2`. Threshold `GROUPING_THRESHOLD = 0.82`. "Visa card top-up failing E5001" + "Visa top-up error E5001 repeatedly" → 1 group, mentions=2.

---

## `report/generator.py` — Phase 5 ✅

**Builds the final markdown complaint report for Product Owners.**

```python
report = generate_report(items, job_name="Social Media")
path   = save_report(report, job_name="Social Media")
```

`generate_report()`:
1. Calls `get_suggested_approach()` (KB RAG) for every item internally — callers don't need to do this
2. Sorts rows by mentions descending (highest-impact first)
3. Calls `llm.chat(fast=False)` once for a 2–3 sentence executive summary
4. Builds the markdown table + header + footer

Report format:
```
# Zalopay Complaint Report — Social Media
**Date**: 2026-06-10 | **Total Issues**: 3 | **Total Mentions**: 6

## Executive Summary
[LLM-generated 2-3 sentences]

## Issue Table
| Domain | Segment | Issue | Mentions | Sources | Suggested Approach |
...
```

`save_report()` writes to `output/<timestamp>_<job>.md`.

---

## `report/guardrails.py` — Phase 5 ✅

**Validates the report before saving/delivering.**

```python
result = check_report(report, items)
# {"ok": True/False, "issues": ["Domain 'X' missing from report", ...]}
```

Checks (only applied when items is non-empty):
- Title starts with `# Zalopay Complaint Report`
- `## Executive Summary` section present
- Issue table header row present
- At least one data row
- Every domain from items appears in the report body

---

## `jobs/jira_job.py` — Phase 6 ✅

**6-step end-to-end pipeline for Jira tickets.**

```python
from jobs.jira_job import run
result = run(dry_run=True)   # uses mock_data
result = run(dry_run=False)  # calls connectors/jira.py (Phase 8)
# returns {"report_path": str, "issues": int, "mentions": int}
```

Steps: fetch → preprocess → extract (LLM) → classify (LLM) → group (embeddings) → report (KB RAG + LLM)

---

## `jobs/social_job.py` — Phase 6 ✅

**8-step end-to-end pipeline for Facebook + Threads posts.**

```python
from jobs.social_job import run
result = run(dry_run=True)   # uses mock_data
result = run(dry_run=False)  # calls connectors/facebook.py + connectors/threads.py
```

Steps: fetch → preprocess → sentiment filter (PhoBERT) → load sample images → extract with image analysis (Vision LLM) → classify (LLM) → group (embeddings) → report (KB RAG + LLM)

Key difference from Jira job: steps 3 (sentiment), 4 (sample images), and the image analysis inside step 5.

---

## `connectors/` — Phase 6 stubs ✅

`jira.py`, `facebook.py`, `threads.py` each have a single `fetch() → list[dict]` function.
Currently raise `RuntimeError` (missing credentials) or `NotImplementedError` (not yet built).
Phase 8 fills in the real API calls — no job code changes needed.

---

## `main.py` — AgentBase entrypoint ✅

**`greennode-agentbase` Custom Agent** served at `POST /invocations` (port 8080). One entrypoint
dispatches on `payload["action"]`; `handle_payload()` is a pure function so it's testable without the SDK.

```bash
python main.py            # runs the AgentBase server (needs Python 3.10+ and the SDK)
# or test the dispatch logic directly:
#   from main import handle_payload
```

**Payloads:**

| Payload | Description |
|---------|-------------|
| `{"action":"run","job":"jira"\|"social"\|"all","dry_run":false}` | Run the pipeline; writes a report + indexes issues. Returns `{status, results}`; one job failing → `status:"partial"` with `errors`. |
| `{"action":"query","question":"..."}` | RAG over the issues store → grounded answer `{status, answer}`. |

`@app.ping` returns `HEALTHY`. The module is import-guarded so it loads even where the SDK is absent
(local Python 3.9), with `app = None`.

## `local_api.py` — local dev harness ✅

The previous **FastAPI server + APScheduler** (endpoints `/health`, `/status`, `/run/jira`, `/run/social`;
daily cron in `Asia/Ho_Chi_Minh`). **Local development only — not shipped in the image.** AgentBase runtimes
are request/response, so scheduling is external/on-demand.

```bash
.venv/bin/uvicorn local_api:app --reload
```

---

## What's Not Built Yet

| Module | Phase | What it will do |
|--------|-------|----------------|
| Real `connectors/jira.py` | 8 | Jira REST API |
| Real `connectors/facebook.py` | 8 | Facebook Graph API |
| Real `connectors/threads.py` | 8 | Threads API |

---

## Related Notes

- [[Projects/Architecture]] — full pipeline diagrams
- [[Projects/Implementation Plan]] — 17-step build order
- [[Projects/Pipeline Deep Dive]] — one post traced through all 10 stages
- [[Concepts/LLM as a Processing Step]] — why many small calls beat one big call
- [[Concepts/Sentiment Analysis]] — PhoBERT + LLM hybrid approach
- [[Concepts/RAG - Retrieval-Augmented Generation]] — how knowledge base search works
