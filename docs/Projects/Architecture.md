# System Architecture

#project #architecture

> [!info] Canonical design: **[[Projects/00 - Project Home]]**. Updated 2026-06-11:
> **single LLM `google/gemma-4-31b-it` via AgentBase MaaS** (the Haiku/Sonnet split below is
> historical). **Trigger = AgentBase `/invocations`**, not the FastAPI/APScheduler shown in the
> Trigger Layer section (that now lives in `local_api.py` for local dev only). Pipeline now adds
> **RAG-grounded classification** and an **agentic Q&A** store.

---

## Two Independent Jobs

```
┌─────────────────────────────────┐   ┌──────────────────────────────────────┐
│         JOB 1: JIRA             │   │        JOB 2: SOCIAL MEDIA           │
│                                 │   │                                      │
│  Trigger: daily 8am / manual    │   │  Trigger: daily 8am / manual         │
│                                 │   │                                      │
│  [Jira API]                     │   │  [Facebook]  [Threads]               │
│       ↓                         │   │       ↓           ↓                  │
│  ── PREPROCESS ──               │   │  Keyword search by terms             │
│  clean_text()                   │   │       ↓                              │
│  deduplicate()                  │   │  ── PREPROCESS ──                    │
│       ↓                         │   │  clean_text()  deduplicate()         │
│  ── ANALYZE ──                  │   │       ↓                              │
│  extract issue                  │   │  ── FILTER ──                        │
│  classify domain/segment        │   │  Sentiment analysis (ML model)       │
│       ↓                         │   │  → keep NEGATIVE only                │
│  ── RAG ──                      │   │       ↓                              │
│  embed issue                    │   │  ── ANALYZE ──                       │
│  search KB → solution           │   │  Image analysis (Claude Vision)      │
│       ↓                         │   │  extract issue                       │
│  ── LLM ──                      │   │  classify domain/segment             │
│  Generate Jira report           │   │       ↓                              │
│       ↓                         │   │  ── RAG ──                           │
│  ── GUARDRAILS ──               │   │  embed issue                         │
│  validate format                │   │  search KB → solution                │
│  check completeness             │   │       ↓                              │
│       ↓                         │   │  ── LLM ──                           │
│  jira_report.md                 │   │  Generate Social report              │
│                                 │   │       ↓                              │
│                                 │   │  ── GUARDRAILS ──                    │
│                                 │   │  validate format                     │
│                                 │   │  hallucination check                 │
│                                 │   │       ↓                              │
│                                 │   │  social_report.md                    │
└──────────────┬──────────────────┘   └──────────────┬────────────────────--─┘
               │                                     │
               └──────────────┬──────────────────────┘
                              ↓
               ┌──────────────────────────┐
               │    output/2026-06-10/    │
               │  ├── jira_report.md      │
               │  └── social_report.md   │
               └──────────────────────────┘
```

---

## Why Separate?

| | Jira Job | Social Media Job |
|--|----------|-----------------|
| Data source | One (Jira API) | Two (Facebook + Threads) |
| Filter | None — all tickets are complaints | Keyword search + sentiment filter |
| Images | No | Yes (Claude Vision) |
| Language | English/internal | Vietnamese + English (user language) |
| Volume | Low (tens/day) | High (hundreds/day) |
| Schedule | Can run independently | Can run independently |
| Can fail independently | Yes | Yes |

---

## Job 1: Jira Pipeline

```
[Trigger]
    ↓
fetch_jira_tickets(since=yesterday)
    ↓
For each ticket:
  ├── extract_issue(title + description)
  ├── classify_domain_segment(text)
  └── search_knowledge_base(issue) → suggested solution
    ↓
generate_jira_report(all_enriched_tickets)
    ↓
save → output/{date}/jira_report.md
```

### Jira-Specific Pipeline Steps

```python
def run_jira_job(days_back: int = 1):
    print("=== JOB 1: Jira ===")

    # 1. Ingest
    tickets = fetch_jira_tickets(days_back)
    print(f"  Fetched {len(tickets)} tickets")

    # 2. Enrich each ticket
    enriched = []
    for ticket in tickets:
        issue     = extract_issue(ticket["text"])
        domain    = classify_domain(ticket["text"])
        segment   = classify_segment(ticket["text"], domain)
        solution  = search_knowledge_base(issue)
        enriched.append({**ticket, "extracted_issue": issue,
                         "domain": domain, "segment": segment,
                         "solution": solution})

    # 3. Generate report
    report = generate_report(enriched, source_label="Jira")
    path   = save_report(report, filename="jira_report.md")
    print(f"  Report saved: {path}")
```

---

## Job 2: Social Media Pipeline

```
[Trigger]
    ↓
fetch_facebook(keywords) + fetch_threads(keywords)   ← parallel
    ↓
sentiment_filter(posts) → keep NEGATIVE only
    ↓
For each post:
  ├── has image? → analyze_image(post_image, sample_images)
  ├── extract_issue(text + image_analysis)
  ├── classify_domain_segment(text + image_analysis)
  └── search_knowledge_base(issue) → suggested solution
    ↓
generate_social_report(all_enriched_posts)
    ↓
save → output/{date}/social_report.md
```

### Social-Specific Pipeline Steps

```python
from concurrent.futures import ThreadPoolExecutor

def run_social_job(days_back: int = 1):
    print("=== JOB 2: Social Media ===")

    # 1. Ingest in parallel
    with ThreadPoolExecutor(max_workers=2) as ex:
        fb_future      = ex.submit(fetch_facebook, days_back)
        threads_future = ex.submit(fetch_threads, days_back)
    raw_posts = fb_future.result() + threads_future.result()
    print(f"  Fetched {len(raw_posts)} posts")

    # 2. Sentiment filter
    negative_posts = [p for p in raw_posts if is_negative(p["text"])]
    print(f"  After filter: {len(negative_posts)} negative posts")

    # 3. Enrich each post
    sample_images = load_sample_images("sample_images/")
    enriched = []
    for post in negative_posts:
        image_analysis = None
        if post.get("images"):
            result         = analyze_post_image(post["images"][0], sample_images)
            image_analysis = result["issue_description"]

        combined_text = f"{post['text']}\n{image_analysis or ''}"
        issue    = extract_issue(combined_text)
        domain   = classify_domain(combined_text)
        segment  = classify_segment(combined_text, domain)
        solution = search_knowledge_base(issue)

        enriched.append({**post, "image_analysis": image_analysis,
                         "extracted_issue": issue, "domain": domain,
                         "segment": segment, "solution": solution})

    # 4. Generate report
    report = generate_report(enriched, source_label="Social Media")
    path   = save_report(report, filename="social_report.md")
    print(f"  Report saved: {path}")
```

---

## How LLM Fits Into the Pipeline

Each processing step uses the LLM differently. See [[Concepts/LLM as a Processing Step]] for the full explanation.

All LLM steps use the single model **`google/gemma-4-31b-it`** (via MaaS). The "fast/smart" tiering in
`llm_client` collapses to this one model in production.

| Step | Uses LLM? | Model | Job |
|------|-----------|-------|-----|
| Fetch data | No — pure API call | — | Both |
| Keyword filter | No — string match | — | Social |
| Sentiment filter | **No** — PhoBERT ML model (LLM tiebreaker only when borderline) | offline model | Social |
| Image analysis | **Yes** — one call per image | Gemma 4 (vision) | Social |
| Extract issue | **Yes** — one call per item | Gemma 4 | Both |
| Classify domain/segment | **Yes** — RAG-grounded, one call each | Gemma 4 | Both |
| RAG lookup (solutions) | No — vector search | — | Both |
| Write report | **Yes** — one call total | Gemma 4 | Both |
| Q&A answer | **Yes** — on `query` action | Gemma 4 | — |

Key rule: **pre-filter with cheap code first, then use LLM on what remains**.
By the time data reaches the LLM, it is already known-relevant.

---

## Shared Components

Both jobs share these — defined once, used by both:

| Component | Used by |
|-----------|---------|
| `classify_domain(text)` | Both |
| `classify_segment(text, domain)` | Both |
| `extract_issue(text)` | Both |
| `search_knowledge_base(query)` | Both (same ChromaDB) |
| `generate_report(items)` | Both (same LLM prompt) |
| `save_report(content, filename)` | Both |

---

## Trigger Layer

> [!warning] Historical (local dev). **Production uses the AgentBase entrypoint** in `main.py`:
> a single `handler(payload, context)` at `POST /invocations` dispatching on `payload["action"]`
> (`run` → `{"job":"jira"|"social"|"all","dry_run":bool}`; `query` → `{"question":...}`). The
> FastAPI + APScheduler code below now lives in `local_api.py` for local development only — AgentBase
> runtimes are request/response, so scheduling is external/on-demand.

```python
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

app = FastAPI()
scheduler = BackgroundScheduler()

# Scheduled: both jobs at 8am every day
scheduler.add_job(run_jira_job,   "cron", hour=8, minute=0,  id="jira_daily")
scheduler.add_job(run_social_job, "cron", hour=8, minute=10, id="social_daily")
scheduler.start()

# Manual trigger endpoints
@app.post("/run/jira")
def trigger_jira():
    run_jira_job()
    return {"status": "ok", "job": "jira"}

@app.post("/run/social")
def trigger_social():
    run_social_job()
    return {"status": "ok", "job": "social"}

@app.post("/run/all")
def trigger_all():
    run_jira_job()
    run_social_job()
    return {"status": "ok", "job": "all"}
```

---

## File Structure

```
project/
├── main.py                    # FastAPI app + scheduler
├── jobs/
│   ├── jira_job.py            # run_jira_job()
│   └── social_job.py          # run_social_job()
├── connectors/
│   ├── jira.py                # fetch_jira_tickets()
│   ├── facebook.py            # fetch_facebook()
│   └── threads.py             # fetch_threads()
├── processors/
│   ├── sentiment.py           # is_negative()
│   ├── image_analyzer.py      # analyze_post_image()
│   ├── classifier.py          # classify_domain(), classify_segment()
│   └── issue_extractor.py     # extract_issue()
├── knowledge_base/
│   ├── index.py               # ChromaDB setup
│   ├── search.py              # search_knowledge_base()
│   └── docs/                  # team-provided solution docs
├── report/
│   └── generator.py           # generate_report(), save_report()
├── sample_images/             # reference images for vision comparison
└── output/
    └── 2026-06-10/
        ├── jira_report.md
        └── social_report.md
```

---

## Build Order

1. `processors/classifier.py` + `processors/issue_extractor.py` (LLM calls, testable alone)
2. `knowledge_base/` — index 5 sample docs, test search
3. `report/generator.py` — test with mock data
4. `jobs/jira_job.py` — wire Job 1 end-to-end with mock Jira data
5. `connectors/jira.py` — replace mock with real Jira API
6. `processors/sentiment.py` — sentiment filter
7. `processors/image_analyzer.py` — Claude Vision
8. `jobs/social_job.py` — wire Job 2 end-to-end with mock social data
9. `connectors/facebook.py` + `connectors/threads.py` — real APIs
10. `main.py` — FastAPI endpoints + scheduler

---

## Related Notes

- [[Projects/Hackathon]] — project overview
- [[Projects/Data Sources]] — connector details for each source
- [[Projects/Image Processing]] — Claude Vision for social images
- [[Projects/Report Format]] — table report structure
- [[Concepts/Tokenization & Text Preprocessing]] — cleaning raw text before processing
- [[Concepts/Embeddings]] — converting text to vectors for RAG + deduplication
- [[Concepts/Sentiment Analysis]] — ML model to filter negative social posts
- [[Concepts/RAG - Retrieval-Augmented Generation]] — knowledge base lookup
- [[Concepts/Guardrails]] — validating LLM output after generation
- [[Concepts/LLM as a Processing Step]] — how LLM fits into each pipeline step
- [[Concepts/LLM API Basics]] — how individual LLM calls are made
