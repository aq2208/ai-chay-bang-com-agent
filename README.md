# ZaloPay Issue Analytics Agent

An AI pipeline that fetches complaints from Jira and social media (Facebook, Threads), filters and classifies them, then generates structured issue reports for Product Owners.

---

## What It Does

Two independent jobs run daily (or on-demand via API):

- **Job 1 — Jira**: Pulls internal support tickets, extracts issues, classifies by domain/segment, searches the knowledge base for solutions, generates a report.
- **Job 2 — Social Media**: Searches Facebook and Threads by keyword, keeps only negative posts (sentiment filter), analyzes any images, extracts and groups issues, generates a report.

Output: a markdown table like this:

| # | Issue | Description | Domain | Segment | Sources | Mentions | Suggested Approach |
|---|-------|-------------|--------|---------|---------|----------|--------------------|
| 1 | Visa top-up failing | Error E5001 after confirming card | Payment | Top-up | FB-2001, TH-3002 | 2 | Check payment gateway... |

---

## Architecture

```
DATA SOURCES
  Jira API ──────────────────────────────────────────────────────┐
  Facebook keyword search ──┐                                    │
  Threads keyword search ───┘                                    │
                             │                                   │
                             ▼                                   ▼
                    ┌─────────────────┐               ┌─────────────────┐
                    │   SOCIAL JOB    │               │    JIRA JOB     │
                    └────────┬────────┘               └────────┬────────┘
                             │                                 │
              ╔══════════════╪═════════════════════════════════╪══════╗
              ║  SHARED PIPELINE STAGES                        │      ║
              ║                                                │      ║
              ║  Stage 1: Preprocess ◄─────────────────────────┘      ║
              ║    clean_text() — remove URLs, emoji, @mentions        ║
              ║    is_meaningful() — drop posts < 4 words              ║
              ║    deduplicate() — fingerprint dedup                   ║
              ║          │                                             ║
              ║  Stage 2: Sentiment filter (Social only)               ║
              ║    PhoBERT ML model → fast pass                        ║
              ║    Claude/Gemini LLM → borderline tiebreaker           ║
              ║    Keep only negative posts                            ║
              ║          │                                             ║
              ║  Stage 3: Image analysis (if images present)           ║
              ║    Claude Vision / Gemini Vision → describe image      ║
              ║    Compare with sample_images/ reference set           ║
              ║          │                                             ║
              ║  Stage 4: Issue extraction                             ║
              ║    LLM → one clean English sentence per post           ║
              ║    e.g. "Visa card top-up failing with error E5001"    ║
              ║          │                                             ║
              ║  Stage 5: Domain classification                        ║
              ║    LLM → Payment | QR Code | Account | ...             ║
              ║                                                        ║
              ║  Stage 6: Segment classification                       ║
              ║    LLM → Top-up | Transfer | Login | OTP | ...        ║
              ║          │                                             ║
              ║  Stage 7: Semantic grouping                            ║
              ║    Embeddings → cosine similarity                      ║
              ║    Merge near-duplicate issues, count mentions         ║
              ║          │                                             ║
              ║  Stage 8: RAG — knowledge base search                  ║
              ║    Embed issue → search ChromaDB                       ║
              ║    Retrieve top-k KB docs → suggested approach         ║
              ║          │                                             ║
              ║  Stage 9: Report generation                            ║
              ║    LLM → markdown table                                ║
              ║          │                                             ║
              ║  Stage 10: Guardrails                                  ║
              ║    Validate format, completeness, no hallucinations    ║
              ╚══════════════╪═════════════════════════════════════════╝
                             │
                    ┌────────▼────────┐
                    │  output/ report │
                    └─────────────────┘

TRIGGER LAYER (not yet built)
  FastAPI  → POST /run/jira    → run Jira job now
           → POST /run/social  → run Social job now
  APScheduler → runs both jobs at 6:00 AM daily
```

---

## File Map

```
clawathon-aicbc-agent/
│
├── config.py              ← all settings: provider, models, domains, thresholds
├── llm_client.py          ← pluggable LLM wrapper (Anthropic / Google / OpenAI)
├── mock_data.py           ← fake Jira tickets + social posts for development
├── test_phase2.py         ← test runner for Phase 2 processors
│
├── processors/            ← one file per pipeline stage
│   ├── preprocessor.py    ← Stage 1: clean, filter, deduplicate (no API)
│   ├── sentiment.py       ← Stage 2: PhoBERT + LLM tiebreaker
│   ├── issue_extractor.py ← Stage 4: LLM → clean English issue sentence
│   └── classifier.py      ← Stages 5+6: LLM → domain → segment
│
├── connectors/            ← data fetchers (Phase 8 — not yet built)
│   ├── jira.py            ← Jira REST API client
│   ├── facebook.py        ← Facebook Graph API keyword search
│   └── threads.py         ← Threads API keyword search
│
├── knowledge_base/        ← RAG system (Phase 3 — not yet built)
│   ├── index.py           ← build ChromaDB index from docs/
│   ├── search.py          ← embed query → find top-k matches
│   └── docs/              ← team writes solution docs here (.md or .txt)
│
├── report/                ← report generation (Phase 5 — not yet built)
│   ├── generator.py       ← LLM → markdown table from grouped issues
│   └── guardrails.py      ← validate report format and completeness
│
├── jobs/                  ← full pipeline runners (Phase 6 — not yet built)
│   ├── jira_job.py        ← runs stages 1,4,5,6,7,8,9,10 on Jira data
│   └── social_job.py      ← runs stages 1,2,3,4,5,6,7,8,9,10 on social data
│
├── sample_images/         ← reference screenshots per domain
│   ├── Payment/
│   ├── QR_Code/
│   ├── Account/
│   ├── App_Performance/
│   └── Merchant/
│
├── output/                ← generated reports land here
├── .env                   ← your secrets (never committed)
├── .env.example           ← template to copy from
└── requirements.txt
```

---

## Local Setup

### 1. Clone and enter the project

```bash
cd clawathon-aicbc-agent
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate      # Mac/Linux
# .venv\Scripts\activate       # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> `torch` is large (~200MB CPU build). First install takes 2–5 minutes.
>
> If `torch` fails, install it explicitly:
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> ```

### 4. Configure your LLM provider

Copy the example env file:

```bash
cp .env.example .env
```

Edit `.env` — choose one provider and paste its key:

```env
# Option A — Google AI Studio (free tier: ~20 req/day)
LLM_PROVIDER=google
LLM_API_KEY=AIzaSy...

# Option B — Anthropic Claude ($5 free credits at console.anthropic.com)
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-api03-...

# Option C — OpenAI
LLM_PROVIDER=openai
LLM_API_KEY=sk-proj-...
```

Model names are set automatically from the provider. Override in `.env` if needed:

```env
MODEL_FAST=gemini-2.5-flash-lite   # cheap model — used for classification
MODEL_SMART=gemini-2.5-pro          # smart model — used for report writing
```

### 5. Verify setup

```bash
.venv/bin/python -c "
from llm_client import llm
print(llm.chat(system='Reply with one word.', user='Say hello', max_tokens=5))
"
```

Expected: `Hello` (or equivalent)

---

## Running Tests

### Test individual pipeline stages

#### Stage 1 — Preprocessor (no API key needed)

```bash
.venv/bin/python -c "
from processors.preprocessor import preprocess
from mock_data import get_mock_social
result = preprocess(get_mock_social())
print(f'{len(result)} posts after cleaning')
for p in result:
    print(' ', p['id'], ':', p['text'][:60])
"
```

#### Stage 2 — Sentiment filter (downloads PhoBERT ~500MB on first run)

```bash
.venv/bin/python -c "
from processors.sentiment import filter_negative
from processors.preprocessor import preprocess
from mock_data import get_mock_social

posts = preprocess(get_mock_social())
negative = filter_negative(posts)
print(f'{len(posts)} total → {len(negative)} negative')
for p in negative:
    print(' KEEP:', p['id'], p['text'][:55])
dropped = [p for p in posts if p not in negative]
for p in dropped:
    print(' DROP:', p['id'], p['text'][:55])
"
```

Expected: 6 kept (negative), 2 dropped (positive).

#### Stage 4 — Issue extraction (requires API key)

```bash
.venv/bin/python -c "
from processors.issue_extractor import extract_issue
cases = [
    'Zalopay bị lỗi rồi! Không nạp tiền được bằng Visa suốt 2 tiếng!!',
    'App ZaloPay crash liên tục khi mở lên',
    'QR code scan failure at merchant terminal',
]
for text in cases:
    print('IN :', text[:60])
    print('OUT:', extract_issue(text))
    print()
"
```

#### Stages 5+6 — Classification (requires API key)

```bash
.venv/bin/python -c "
from processors.classifier import classify_domain, classify_segment
issues = [
    'Visa card top-up failing with error E5001',
    'QR code scan failure at merchant terminal',
    'OTP not received after login attempt',
    'App crashes on launch — Android device',
]
for issue in issues:
    domain  = classify_domain(issue)
    segment = classify_segment(issue, domain)
    print(f'{domain:15} / {segment:12} ← {issue}')
"
```

### Run the full Phase 2 test suite

```bash
.venv/bin/python test_phase2.py
```

### Build the knowledge base index (Phase 3 — no API key needed)

```bash
.venv/bin/python knowledge_base/index.py
```

Expected output:
```
Indexed 17 chunks from 5 docs → ChromaDB at .../chroma_db
  • account.md  (4 chunks)
  • app_performance.md  (3 chunks)
  ...
```

### Test the knowledge base search

```bash
.venv/bin/python test_phase3.py
```

This builds the index then runs 4 search tests — no API key needed. Takes ~5 seconds.

To test a single search manually:

```bash
.venv/bin/python -c "
from knowledge_base.index import build_index
from knowledge_base.search import get_suggested_approach
build_index()
print(get_suggested_approach('Visa payment failed with error E5001.'))
"
```

This runs all four processors in sequence. On first run, PhoBERT (~500MB) downloads automatically.

> **Google free tier note**: The free tier allows ~10–20 requests/minute/day depending on the model.
> The test suite makes ~14 LLM calls total. If you hit a rate limit, the client automatically
> waits and retries. Full run may take 2–3 minutes on free tier.

---

## How the Pipeline Flows (Code Trace)

Here is what happens when the Social job runs on one Facebook post:

```
INPUT:
  {"id": "FB-2001", "source": "facebook",
   "text": "Zalopay bị lỗi rồi! Không nạp tiền được bằng Visa suốt 2 tiếng!!",
   "images": [], "timestamp": "2026-06-10T08:30:00"}

Stage 1 — preprocessor.py
  clean_text()       → "Zalopay bị lỗi rồi Không nạp tiền được bằng Visa suốt 2 tiếng"
  is_meaningful()    → True (10 words ≥ 4)
  deduplicate()      → kept (first 80 chars not seen before)

Stage 2 — sentiment.py
  PhoBERT model      → {"label": "NEG", "score": 0.94}
  score ≥ 0.75       → True, skip LLM tiebreaker
  is_negative()      → True → POST KEPT

Stage 3 — image_analyzer.py (not built yet)
  images = []        → skipped, image_description = ""

Stage 4 — issue_extractor.py
  LLM call (fast)    → "Visa payment failing for two hours with error code."
  
Stage 5 — classifier.py → classify_domain()
  LLM call (fast)    → "Payment"

Stage 6 — classifier.py → classify_segment()
  LLM call (fast)    → "Top-up"

Stage 7 — grouper.py (not built yet)
  Embedding of issue → [0.12, -0.34, ...]
  Cosine similarity  → matches TH-3002 (same issue, score 0.91 > threshold 0.82)
  Merged into group  → mentions = 2, sources = [FB-2001, TH-3002]

Stage 8 — knowledge_base/search.py (not built yet)
  Embed issue        → search ChromaDB
  Top match          → "payment-gateway-errors.md" (similarity 0.87)
  Suggested approach → "Check payment gateway timeout config..."

Stage 9 — report/generator.py (not built yet)
  LLM call (smart)   → builds markdown table row

Stage 10 — report/guardrails.py (not built yet)
  Validate row       → all columns present, no hallucination markers

OUTPUT ROW:
  | 1 | Visa top-up failing | Error code reported, 2+ hours... | Payment | Top-up |
    FB-2001, TH-3002 | 2 | Check payment gateway timeout... |
```

---

## LLM Provider Reference

| Provider | Key format | Free tier | Speed | Best for |
|----------|-----------|-----------|-------|----------|
| `google` | `AIzaSy...` | 10–20 req/day | Fast | Testing (free) |
| `anthropic` | `sk-ant-api03-...` | $5 credit on signup | Medium | Production |
| `openai` | `sk-proj-...` | $5 credit on signup | Medium | Production |

To switch providers, change two lines in `.env` — no code changes needed:

```env
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-api03-...
```

---

## Build Status

| Phase | What | Status |
|-------|------|--------|
| 1 | Project skeleton, config, mock data | ✅ Done |
| 2 | Preprocessor, sentiment, issue extractor, classifier | ✅ Done |
| 3 | Knowledge base — 5 docs, 17 chunks, ChromaDB search | ✅ Done |
| 4 | Image analyzer, semantic grouper | ⬜ Next |
| 5 | Report generator, guardrails | ⬜ Pending |
| 6 | Job runners (jira_job.py, social_job.py) | ⬜ Pending |
| 7 | FastAPI + APScheduler trigger layer | ⬜ Pending |
| 8 | Real data connectors (Jira, FB, Threads APIs) | ⬜ Pending |

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_PROVIDER` | Yes | `anthropic` \| `google` \| `openai` |
| `LLM_API_KEY` | Yes | API key for the chosen provider |
| `MODEL_FAST` | No | Override fast model name (default auto per provider) |
| `MODEL_SMART` | No | Override smart model name (default auto per provider) |
| `JIRA_URL` | Phase 8 | Your Jira instance URL |
| `JIRA_EMAIL` | Phase 8 | Jira account email |
| `JIRA_API_TOKEN` | Phase 8 | Jira API token |
| `FB_PAGE_ID` | Phase 8 | Facebook page ID to search |
| `FB_ACCESS_TOKEN` | Phase 8 | Facebook Graph API token |
| `THREADS_ACCESS_TOKEN` | Phase 8 | Threads API token |

---

## Key Design Decisions

**Pipeline, not a conversational agent.** Each stage is a small, focused LLM call. This is cheaper, faster, and easier to debug than one giant prompt.

**PhoBERT before LLM for sentiment.** The ML model handles ~80% of cases in milliseconds for free. LLM is only called for the borderline 20%.

**Two independent jobs.** Jira and Social can fail, be triggered, and be scheduled independently. A Facebook API outage doesn't block the Jira report.

**Pluggable LLM.** All LLM calls go through `llm_client.py`. Swap providers in `.env` — zero code changes.

**Mock data for development.** `mock_data.py` provides realistic test data so you can develop and test every stage without real API credentials.
