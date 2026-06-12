# Architecture Review

#project #review

> [!info] Canonical design: **[[Projects/00 - Project Home]]**. Updated 2026-06-11: LLM = single
> **`google/gemma-4-31b-it` via AgentBase MaaS**; deploy = **AgentBase Custom Agent** (`/invocations`),
> not FastAPI/Streamlit. The gaps below were addressed; classification is now **RAG-grounded** and an
> **agentic Q&A** endpoint was added.

---

## Overall Verdict

The architecture is **solid for a hackathon**. The two-job split, pipeline approach, RAG for KB, and Claude for vision are all correct decisions. However, there are **7 gaps** that will cause problems during the demo if not addressed.

---

## ✅ What's Right

| Decision | Why It's Good |
|----------|--------------|
| Pipeline, not conversational agent | Batch job doesn't need a while-loop. Simpler and more predictable. |
| Two independent jobs | Can fail/retry/trigger independently. Clean separation of concerns. |
| Mock data first | Real social APIs need app approval. Mocks let you build and demo without waiting. |
| Claude Sonnet for vision | No extra model, no extra API, native multimodal. Reduces complexity. |
| Claude Haiku for classification | 10x cheaper than Sonnet for yes/no tasks. Right tool for the job. |
| ChromaDB for RAG | Local, free, zero infra. Perfect for hackathon. |
| ML model for sentiment | Fast, free, offline. Don't burn LLM API budget on simple filtering. |
| Preprocess before LLM | Cleans noise before the expensive step. Correct order. |
| Guardrails after LLM | Catches hallucinations and format errors before saving. |
| FastAPI + APScheduler | Standard, well-documented, easy to demo. |

---

## ❌ Gap 1 — Inconsistency: Sentiment Analysis

**Problem:** The Architecture note's LLM table says sentiment uses "Haiku (LLM)" but the Sentiment Analysis concept note says "use ML model (PhoBERT) first". These contradict each other.

**Fix:** Sentiment analysis = **ML model (PhoBERT)** always. Only fall back to LLM if score is borderline (0.4–0.7). Update the Architecture table.

```
Sentiment filter → PhoBERT ML model (not Haiku)
                   └── if borderline → Haiku as tiebreaker
```

---

## ❌ Gap 2 — Missing: Cross-Source Deduplication & Mention Grouping

**Problem:** The pipeline produces one enriched item per raw post. If Jira ticket-1234 AND 4 Facebook posts all report "Visa top-up failing", the report will show 5 separate rows instead of 1 row with `mentions=5`.

**Fix:** After enriching all items, add a **semantic grouping step** before report generation:

```python
# After enrichment, before report generation:
grouped = group_by_similarity(enriched_items, threshold=0.82)
# Each group becomes ONE row in the report with mentions = len(group)
# Sources field lists all unique sources in the group: "Jira, FB, Threads"
```

This uses the embeddings we already have. The `cluster_by_similarity()` function is in `Concepts/Embeddings.md` — just integrate it into the pipeline.

**This is important** — without it, the report inflates issue counts and misrepresents severity.

---

## ❌ Gap 3 — Missing: Async Job Execution in FastAPI

**Problem:** The current trigger endpoints block the HTTP request for the entire job duration. A job might take 3–5 minutes. The browser/caller will time out.

```python
# ❌ Current — blocks for 5 minutes
@app.post("/run/jira")
def trigger_jira():
    run_jira_job()  # caller waits here
    return {"status": "ok"}
```

**Fix:** Run jobs as background tasks. Return immediately, let the job run asynchronously.

```python
from fastapi import BackgroundTasks

@app.post("/run/jira")
def trigger_jira(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_jira_job)
    return {"status": "started", "job": "jira"}

# Add a status endpoint so the caller can check if it's done
job_status = {}

def run_jira_job_tracked():
    job_status["jira"] = "running"
    run_jira_job()
    job_status["jira"] = "done"

@app.get("/status")
def get_status():
    return job_status
```

---

## ❌ Gap 4 — Missing: Configuration & Secrets Management

**Problem:** API keys for Jira, Anthropic, Facebook, Threads are not addressed anywhere. Hardcoding them is a security issue. No `.env` setup defined.

**Fix:** Use a `.env` file loaded by `python-dotenv`:

```bash
pip install python-dotenv
```

```python
# .env (never commit this to git)
ANTHROPIC_API_KEY=sk-ant-...
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your@email.com
JIRA_API_TOKEN=...
FACEBOOK_PAGE_ID=...
FACEBOOK_ACCESS_TOKEN=...
THREADS_ACCESS_TOKEN=...
```

```python
# config.py
from dotenv import load_dotenv
import os

load_dotenv()

ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY")
JIRA_URL            = os.getenv("JIRA_URL")
JIRA_EMAIL          = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN      = os.getenv("JIRA_API_TOKEN")
FACEBOOK_PAGE_ID    = os.getenv("FACEBOOK_PAGE_ID")
```

Add `.env` to `.gitignore` immediately.

---

## ❌ Gap 5 — Missing: Error Handling in the Pipeline

**Problem:** If one item fails (broken image URL, Jira API timeout, LLM rate limit), the whole job crashes. No error handling exists in the pipeline code.

**Fix:** Wrap per-item processing in try/except so one bad item doesn't kill the job:

```python
enriched = []
failed = []

for item in items:
    try:
        issue    = extract_issue(item["text"])
        domain   = classify_domain(item["text"])
        segment  = classify_segment(item["text"], domain)
        solution = search_knowledge_base(issue)
        enriched.append({**item, "extracted_issue": issue,
                         "domain": domain, "segment": segment,
                         "solution": solution})
    except Exception as e:
        failed.append({"item": item["id"], "error": str(e)})
        print(f"  ⚠️  Skipped {item['id']}: {e}")

print(f"  Processed: {len(enriched)} ok, {len(failed)} failed")
```

---

## ❌ Gap 6 — Missing: Knowledge Base Content Definition

**Problem:** RAG is fully implemented technically, but we haven't defined **what docs go into the KB**. Without KB content, `search_knowledge_base()` returns nothing useful.

**Fix:** Team needs to prepare KB docs before coding begins. Suggested format:

```markdown
<!-- knowledge_base/docs/payment_e5001.md -->
# E5001 — Payment Gateway Timeout

**Issue type:** Payment failure  
**Domain:** Payment  
**Segment:** Top-up, Transfer  

**Cause:** Payment gateway 3DS authentication times out when processing Visa cards 
during high traffic periods.

**Suggested Approach:**
1. Increase 3DS timeout from 10s to 30s in gateway config
2. Add a retry button in the UI (max 3 retries)
3. If persists, escalate to payment gateway provider with transaction logs

**Related error codes:** E5001, E5002
```

Each doc = one known issue type. Target: 20–30 docs covering your main issue categories.

---

## ❌ Gap 7 — Missing: Report Output Delivery

**Problem:** Reports are saved as `.md` files in `output/`. But how does the PO actually *receive* them? The vault doesn't define this.

**Options (pick one for the demo):**

| Option | Effort | Demo quality |
|--------|--------|-------------|
| Simple web page (Streamlit) to view reports | Low | Good |
| Email the report (SMTP / SendGrid) | Medium | Very good |
| Slack message with report link | Medium | Very good |
| Just show the `.md` file | None | Poor for demo |

**Recommendation for hackathon:** Streamlit page that shows the latest report with a "Run Now" button. One file, 30 lines of code.

```python
# dashboard.py
import streamlit as st
import glob, os

st.title("Daily Issue Report")

# Show latest report
reports = sorted(glob.glob("output/**/*.md", recursive=True))
if reports:
    latest = reports[-1]
    st.markdown(f"**Latest:** `{latest}`")
    with open(latest) as f:
        st.markdown(f.read())

# Manual trigger buttons
col1, col2 = st.columns(2)
if col1.button("▶ Run Jira Job"):
    import requests
    requests.post("http://localhost:8000/run/jira")
    st.success("Jira job started!")

if col2.button("▶ Run Social Job"):
    import requests
    requests.post("http://localhost:8000/run/social")
    st.success("Social job started!")
```

---

## Complete Tech Stack (Revised)

| Layer | Component | Choice | Notes |
|-------|-----------|--------|-------|
| **LLM** | All text + vision | `google/gemma-4-31b-it` via MaaS | Single platform model (OpenAI-compatible) |
| **LLM** | Local/Colab dev | Google Gemini (`google-genai`) | Free-tier stage testing |
| **Classification** | RAG grounding | `taxonomy` ChromaDB collection | Grounds domain/segment in known examples |
| **NLP** | Sentiment analysis | `wonrax/phobert-base-vietnamese-sentiment` | Vietnamese ML model, offline |
| **NLP** | Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` | Vietnamese + English |
| **Vector DB** | RAG + dedup | ChromaDB (persistent) | Local, free |
| **Connectors** | Jira | `jira` Python lib | Official API |
| **Connectors** | Facebook | `requests` + Graph API | Manual HTTP |
| **Connectors** | Threads | `requests` + Threads API | Manual HTTP |
| **API** | Trigger layer | FastAPI + BackgroundTasks | Async job execution |
| **Scheduler** | Daily runs | APScheduler | Cron-style |
| **Config** | Secrets | `python-dotenv` + `.env` | Never commit |
| **Validation** | Guardrails | Pydantic + custom validators | Format + hallucination |
| **UI** | Report viewer | Streamlit | Demo dashboard |
| **Output** | Reports | Markdown files | Per-date folder |

---

## Revised Pipeline (Both Jobs)

```
FETCH           → pure API/mock, parallel where possible
    ↓
PREPROCESS      → clean_text(), deduplicate(), length filter
    ↓
FILTER          → keyword match (social) + PhoBERT sentiment (social)
    ↓
ENRICH          → image analysis, issue extraction, domain/segment classify
    ↓
RAG LOOKUP      → embed issue, search ChromaDB, retrieve solution text
    ↓
SEMANTIC GROUP  → cluster similar issues, count mentions, merge sources   ← NEW
    ↓
LLM REPORT      → one Sonnet call, receives grouped structured data
    ↓
GUARDRAILS      → format, completeness, hallucination check, retry if fail
    ↓
SAVE            → output/{date}/jira_report.md or social_report.md
    ↓
DELIVER         → Streamlit dashboard shows latest report
```

---

## Revised File Structure

```
project/
├── .env                       # secrets — never commit
├── .env.example               # template — commit this
├── config.py                  # loads .env, exposes constants
├── main.py                    # FastAPI app + APScheduler
├── dashboard.py               # Streamlit UI
├── jobs/
│   ├── jira_job.py
│   └── social_job.py
├── connectors/
│   ├── jira.py
│   ├── facebook.py
│   └── threads.py
├── processors/
│   ├── preprocessor.py        # clean_text(), deduplicate()
│   ├── sentiment.py           # PhoBERT model
│   ├── image_analyzer.py      # Claude Vision
│   ├── classifier.py          # domain + segment (Haiku)
│   ├── issue_extractor.py     # extract_issue() (Haiku)
│   └── grouper.py             # semantic grouping (embeddings) ← NEW
├── knowledge_base/
│   ├── index.py
│   ├── search.py
│   └── docs/                  # 20-30 solution docs (team writes these)
├── report/
│   ├── generator.py
│   └── guardrails.py          # ← NEW separate file
├── sample_images/
│   ├── Payment/
│   ├── QR_Code/
│   └── Account/
└── output/
    └── {date}/
        ├── jira_report.md
        └── social_report.md
```

---

## Revised Build Order

| Step | What | Who |
|------|------|-----|
| 0 | Write 10 KB docs + prepare 5 sample images | Everyone (content, not code) |
| 1 | `config.py` + `.env` setup | Anyone |
| 2 | `processors/preprocessor.py` — text cleaning | Person A |
| 3 | `processors/sentiment.py` — PhoBERT | Person A |
| 4 | `processors/classifier.py` + `issue_extractor.py` | Person B |
| 5 | `knowledge_base/` — index KB docs, test search | Person C |
| 6 | `processors/grouper.py` — semantic clustering | Person C |
| 7 | `report/generator.py` + `guardrails.py` — test with mock data | Person D |
| 8 | `jobs/jira_job.py` — wire Job 1 end-to-end | Person B |
| 9 | `processors/image_analyzer.py` — Claude Vision | Person A |
| 10 | `jobs/social_job.py` — wire Job 2 end-to-end | Person B |
| 11 | `main.py` — FastAPI async + APScheduler | Person D |
| 12 | `dashboard.py` — Streamlit UI | Person D |
| 13 | `connectors/jira.py` — real Jira API | Person A |
| 14 | `connectors/facebook.py` + `threads.py` | Person B |

**Start coding at Step 2, not Step 13.** Real APIs come last.

---

## Pre-Coding Prerequisites (Do Before Any Code)

These must be done by the team before coding starts or the pipeline has nothing to work with:

- [ ] **KB docs**: Write 20–30 solution docs in `knowledge_base/docs/`
- [ ] **Sample images**: Collect 5–10 reference screenshots per domain in `sample_images/`
- [ ] **Domain/segment list**: Agree on final domain + segment taxonomy
- [ ] **Keywords list**: Agree on keywords for social media search
- [ ] **API credentials**: Get Jira API token. Facebook/Threads tokens if using real APIs.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Facebook/Threads API approval takes too long | High | High | Use mock data for demo |
| PhoBERT misclassifies Vietnamese sarcasm | Medium | Medium | Add LLM tiebreaker for borderline cases |
| LLM hallucinates issues in report | Medium | High | Guardrails hallucination check |
| KB docs not ready before demo | Medium | High | Start writing them Day 1 |
| Image analysis too slow for large batches | Low | Medium | Parallelize with ThreadPoolExecutor |
| ChromaDB loses data between restarts | Low | Low | Use PersistentClient (already planned) |

---

## Related Notes

- [[Projects/Hackathon]] — project overview
- [[Projects/Architecture]] — full pipeline diagrams
- [[Projects/Data Sources]] — connectors
- [[Projects/Image Processing]] — Claude Vision
- [[Projects/Report Format]] — output table structure
- [[Concepts/Embeddings]] — semantic grouping
- [[Concepts/Sentiment Analysis]] — PhoBERT
- [[Concepts/Guardrails]] — output validation
