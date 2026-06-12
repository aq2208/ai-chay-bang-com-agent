# Implementation Plan

#project #plan

> [!info] Canonical design: **[[Projects/00 - Project Home]]**. Updated 2026-06-11. This was the original
> build plan; the project is now mostly built and **re-targeted onto AgentBase**. Notable deltas vs. below:
> deps use **`greennode-agentbase` + `openai`** (MaaS), not `anthropic`; models = **`google/gemma-4-31b-it`**;
> **Phase 7 trigger = AgentBase `/invocations`** (the FastAPI/APScheduler code is now `local_api.py`,
> local-dev only); added **RAG-grounded classification** (taxonomy collection) and **agentic Q&A**
> (`issues_store.py`). For current status see the homepage Build Status table.

---

## Core Principle

> **Build the smallest testable thing first. Every file you write should be runnable and verifiable before moving to the next.**

Never build connectors before processors. Never build jobs before processors. Never wire the full pipeline before each piece works alone.

---

## Dependency Graph

```
config.py
    └── ALL other files depend on this
    
mock_data.py
    └── Used for testing until real APIs are wired

preprocessor.py
    └── sentiment.py
    └── issue_extractor.py
    └── classifier.py
    └── image_analyzer.py

knowledge_base/index.py + docs/
    └── knowledge_base/search.py
            └── grouper.py (uses same embedder)

processors/* (all 4)
knowledge_base/search.py
    └── jobs/jira_job.py
    └── jobs/social_job.py

report/generator.py
report/guardrails.py
    └── jobs/jira_job.py
    └── jobs/social_job.py

jobs/jira_job.py
jobs/social_job.py
    └── main.py (FastAPI)
    └── dashboard.py (Streamlit)

connectors/* (wired last — replaces mock_data)
```

---

## Phase 0 — Before Any Code (Day 1 Morning, Whole Team)

These are **content tasks**, not coding. Nothing works without them.

| Task | Who | Output |
|------|-----|--------|
| Agree on final domain list | All | e.g. Payment, QR Code, Account, App Performance, Merchant, Other |
| Agree on segment list per domain | All | e.g. Payment → Top-up, Transfer, Withdrawal, Billing |
| Agree on keywords for social search | All | e.g. ["zalopay", "ví zalopay", "nạp tiền lỗi"] |
| Write 15–20 KB solution docs | All | `knowledge_base/docs/*.md` |
| Collect 5–10 sample images per domain | All | `sample_images/Payment/*.png`, etc. |
| Create `.env` with all keys | All | ANTHROPIC_API_KEY, JIRA_*, FB_*, etc. |

**KB doc format:**
```markdown
# [Issue Name]
**Domain:** Payment
**Segment:** Top-up
**Error codes:** E5001, E5002

## Cause
[What causes this issue]

## Suggested Approach
1. [Step 1]
2. [Step 2]
3. [Escalation path]
```

Do not skip this phase. RAG and image analysis are useless without this content.

---

## Phase 1 — Foundation (Day 1)

Build the skeleton every other file imports from.

### Step 1 — Project setup
```
project/
├── requirements.txt
├── .env               (gitignored)
├── .env.example       (committed)
└── config.py
```

**`requirements.txt`:**
```
anthropic
python-dotenv
fastapi
uvicorn
apscheduler
streamlit
chromadb
sentence-transformers
transformers
torch
jira
requests
pydantic
```

**`config.py`:**
```python
from dotenv import load_dotenv
import os

load_dotenv()

ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
JIRA_URL           = os.getenv("JIRA_URL")
JIRA_EMAIL         = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN     = os.getenv("JIRA_API_TOKEN")
FB_PAGE_ID         = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN    = os.getenv("FB_ACCESS_TOKEN")
THREADS_TOKEN      = os.getenv("THREADS_TOKEN")

DOMAINS  = ["Payment", "QR Code", "Account", "App Performance", "Merchant", "Other"]
SEGMENTS = {
    "Payment":         ["Top-up", "Transfer", "Withdrawal", "Billing"],
    "QR Code":         ["Payment", "Generation", "Merchant"],
    "Account":         ["Login", "OTP", "Registration", "Profile"],
    "App Performance": ["Crash", "Loading", "UI Bug"],
    "Merchant":        ["POS", "Settlement", "Onboarding"],
    "Other":           ["General"],
}
KEYWORDS = ["zalopay", "ví zalopay", "nạp tiền lỗi", "thanh toán lỗi"]
```

**Test:** `python -c "import config; print(config.ANTHROPIC_API_KEY[:10])"` — should print partial key.

---

### Step 2 — Mock data
File: `mock_data.py`

```python
MOCK_JIRA = [
    {"id": "JIRA-1001", "source": "jira",
     "text": "User reports Visa card top-up failing. Error E5001 appears after entering card details.",
     "images": [], "timestamp": "2026-06-10T09:00:00"},
    {"id": "JIRA-1002", "source": "jira",
     "text": "QR code scan not working at Highlands Coffee merchant. Multiple users affected.",
     "images": [], "timestamp": "2026-06-10T10:00:00"},
    {"id": "JIRA-1003", "source": "jira",
     "text": "OTP not received on registered phone number. User waited 15 minutes.",
     "images": [], "timestamp": "2026-06-10T11:00:00"},
]

MOCK_SOCIAL = [
    {"id": "FB-2001", "source": "facebook",
     "text": "Zalopay bị lỗi rồi! Không nạp tiền được bằng Visa suốt 2 tiếng!!",
     "images": ["https://example.com/screenshot_e5001.jpg"],
     "timestamp": "2026-06-10T08:30:00"},
    {"id": "FB-2002", "source": "facebook",
     "text": "Great app, been using ZaloPay for years!",   # positive — filtered out
     "images": [], "timestamp": "2026-06-10T08:45:00"},
    {"id": "FB-2003", "source": "facebook",
     "text": "Quét QR không được tại Circle K. Đứng xếp hàng mà thanh toán không qua.",
     "images": [], "timestamp": "2026-06-10T07:15:00"},
    {"id": "TH-3001", "source": "threads",
     "text": "ZaloPay không gửi OTP về điện thoại. Đăng nhập không được luôn.",
     "images": [], "timestamp": "2026-06-10T07:00:00"},
    {"id": "TH-3002", "source": "threads",
     "text": "App bị crash khi mở lên. Điện thoại Samsung Galaxy S21.",
     "images": [], "timestamp": "2026-06-10T06:45:00"},
]

def get_mock_jira():   return MOCK_JIRA.copy()
def get_mock_social(): return MOCK_SOCIAL.copy()
```

**Test:** `python -c "from mock_data import get_mock_jira; print(len(get_mock_jira()))"` → `3`

---

## Phase 2 — Core Processors (Day 1–2)

Each file is independently testable. Build and test one before moving to the next.

### Step 3 — Preprocessor
File: `processors/preprocessor.py`

```python
import re

def clean_text(text: str) -> str:
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'#\w+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'[^\w\s\-À-ɏḀ-ỿ]', ' ', text)  # keep Vietnamese
    text = re.sub(r'[!?]{2,}', '!', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_meaningful(text: str, min_words: int = 4) -> bool:
    return len(text.split()) >= min_words

def deduplicate(items: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for item in items:
        key = item["text"][:80].lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique

def preprocess(items: list[dict]) -> list[dict]:
    result = []
    for item in items:
        cleaned = clean_text(item["text"])
        if is_meaningful(cleaned):
            result.append({**item, "text": cleaned})
    return deduplicate(result)
```

**Test:**
```python
from processors.preprocessor import clean_text
print(clean_text("Zalopay bị lỗi rồi!!!! 😡😡 http://fb.com/123"))
# → "Zalopay bị lỗi rồi!"
```

---

### Step 4 — Sentiment Analysis
File: `processors/sentiment.py`

```python
from transformers import pipeline as hf_pipeline
import anthropic
from config import ANTHROPIC_API_KEY

# Load once at module level (not per call)
_sentiment_model = hf_pipeline(
    "text-classification",
    model="wonrax/phobert-base-vietnamese-sentiment"
)
_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def is_negative(text: str) -> bool:
    result = _sentiment_model(text[:512])[0]
    label, score = result["label"], result["score"]

    if label == "NEG" and score >= 0.75: return True
    if label == "POS" and score >= 0.75: return False

    # Borderline — use LLM as tiebreaker
    resp = _client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=5,
        system="Is this text a complaint or problem report? Reply YES or NO only.",
        messages=[{"role": "user", "content": text}]
    )
    return "YES" in resp.content[0].text.upper()
```

**Test:**
```python
from processors.sentiment import is_negative
print(is_negative("Không nạp tiền được bằng Visa suốt 2 tiếng!"))  # True
print(is_negative("Great app, love using ZaloPay!"))               # False
```

---

### Step 5 — Issue Extractor
File: `processors/issue_extractor.py`

```python
import anthropic
from config import ANTHROPIC_API_KEY

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def extract_issue(text: str, image_description: str = "") -> str:
    combined = text
    if image_description:
        combined += f"\n[Image shows: {image_description}]"

    resp = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=60,
        system="""Extract the core technical issue from this user complaint.
Output one clear English sentence, 8-15 words.
Focus on: what failed, which feature, any error code.
No emotional language.""",
        messages=[{"role": "user", "content": combined}]
    )
    return resp.content[0].text.strip()
```

**Test:**
```python
from processors.issue_extractor import extract_issue
print(extract_issue("Không nạp tiền được bằng Visa suốt 2 tiếng, lỗi E5001"))
# → "Visa card top-up failing with error E5001"
```

---

### Step 6 — Classifier
File: `processors/classifier.py`

```python
import anthropic
from config import ANTHROPIC_API_KEY, DOMAINS, SEGMENTS

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def classify_domain(issue: str) -> str:
    resp = _client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=10,
        system=f"Classify into exactly one domain. Reply with the name only.\nDomains: {', '.join(DOMAINS)}",
        messages=[{"role": "user", "content": issue}]
    )
    label = resp.content[0].text.strip()
    return label if label in DOMAINS else "Other"

def classify_segment(issue: str, domain: str) -> str:
    options = SEGMENTS.get(domain, ["General"])
    resp = _client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=10,
        system=f"Classify into exactly one segment. Reply with the name only.\nSegments: {', '.join(options)}",
        messages=[{"role": "user", "content": issue}]
    )
    label = resp.content[0].text.strip()
    return label if label in options else options[0]
```

**Test:**
```python
from processors.classifier import classify_domain, classify_segment
domain = classify_domain("Visa card top-up failing with error E5001")
print(domain)                             # Payment
print(classify_segment("...", domain))    # Top-up
```

---

## Phase 3 — Knowledge Base (Day 2)

### Step 7 — Index KB docs
File: `knowledge_base/index.py`

```python
import chromadb
from sentence_transformers import SentenceTransformer
from pathlib import Path

_embedder   = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
_db         = chromadb.PersistentClient(path="./chroma_db")
_collection = _db.get_or_create_collection("knowledge_base")

def index_docs(docs_folder: str = "knowledge_base/docs"):
    """Call once to index all KB docs. Re-run when docs change."""
    _collection.delete(where={"source": {"$exists": True}})  # clear old
    for path in Path(docs_folder).glob("*.md"):
        text = path.read_text(encoding="utf-8")
        vec  = _embedder.encode(text).tolist()
        _collection.add(documents=[text], embeddings=[vec], ids=[path.stem],
                        metadatas=[{"source": path.stem}])
    print(f"Indexed {len(list(Path(docs_folder).glob('*.md')))} docs")
```

**`knowledge_base/search.py`:**
```python
from knowledge_base.index import _collection, _embedder

def search_knowledge_base(issue: str, n_results: int = 2) -> str:
    vec     = _embedder.encode(issue).tolist()
    results = _collection.query(query_embeddings=[vec], n_results=n_results)
    docs    = results["documents"][0]
    dists   = results["distances"][0]
    relevant = [d for d, s in zip(docs, dists) if s < 0.6]
    return "\n---\n".join(relevant) if relevant else "No known solution. Escalate to engineering."
```

**Test:**
```python
from knowledge_base.index import index_docs
from knowledge_base.search import search_knowledge_base
index_docs()
print(search_knowledge_base("Visa card top-up failing with E5001"))
# → should return your E5001 KB doc content
```

---

## Phase 4 — Image Analyzer & Grouper (Day 2–3)

### Step 8 — Image Analyzer
File: `processors/image_analyzer.py`

```python
import anthropic, json, base64
from pathlib import Path
from config import ANTHROPIC_API_KEY

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def load_sample_images(folder: str = "sample_images") -> list[dict]:
    samples = []
    for path in Path(folder).rglob("*.png"):
        data  = base64.standard_b64encode(path.read_bytes()).decode()
        label = path.stem.replace("_", " ")
        domain= path.parent.name
        samples.append({"data": data, "label": label, "domain": domain})
    return samples

def analyze_image(image_url: str, samples: list[dict]) -> dict:
    content = [
        {"type": "image", "source": {"type": "url", "url": image_url}},
        {"type": "text",  "text": "User screenshot. Compare with samples below:"}
    ]
    for s in samples:
        content += [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": s["data"]}},
            {"type": "text",  "text": f"Sample: {s['label']} (Domain: {s['domain']})"}
        ]
    content.append({"type": "text", "text":
        'Answer in JSON: {"issue_description":"...","matched_sample":"...","domain":"...","confidence":"high/medium/low"}'})

    resp = _client.messages.create(model="claude-sonnet-4-6", max_tokens=300,
                                   messages=[{"role": "user", "content": content}])
    text = resp.content[0].text
    return json.loads(text[text.find("{"):text.rfind("}")+1])
```

---

### Step 9 — Semantic Grouper
File: `processors/grouper.py`

```python
import numpy as np
from knowledge_base.index import _embedder   # reuse same embedder

def _cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def group_similar(items: list[dict], threshold: float = 0.82) -> list[dict]:
    if not items: return []
    issues  = [i["extracted_issue"] for i in items]
    vectors = _embedder.encode(issues)
    used, groups = set(), []

    for i, vi in enumerate(vectors):
        if i in used: continue
        cluster = [items[i]]
        used.add(i)
        for j, vj in enumerate(vectors):
            if j not in used and _cosine(vi, vj) >= threshold:
                cluster.append(items[j]); used.add(j)

        rep = cluster[0].copy()
        rep["mentions"] = len(cluster)
        rep["sources"]  = ", ".join(sorted({c["source"] for c in cluster}))
        rep["raw_ids"]  = [c["id"] for c in cluster]
        groups.append(rep)

    return sorted(groups, key=lambda x: x["mentions"], reverse=True)
```

**Test:**
```python
from processors.grouper import group_similar
items = [
    {"id": "a", "source": "facebook", "extracted_issue": "Visa top-up failing E5001"},
    {"id": "b", "source": "jira",     "extracted_issue": "Visa card top-up error E5001"},
    {"id": "c", "source": "threads",  "extracted_issue": "Cannot add money with Visa"},
]
groups = group_similar(items)
print(len(groups))          # 1 (all merged)
print(groups[0]["mentions"])# 3
print(groups[0]["sources"]) # "facebook, jira, threads"
```

---

## Phase 5 — Report Generator (Day 3)

### Step 10 — Generator
File: `report/generator.py`

```python
import anthropic
from datetime import datetime
from config import ANTHROPIC_API_KEY

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def generate_report(grouped_items: list[dict], source_label: str) -> str:
    date    = datetime.now().strftime("%Y-%m-%d")
    summary = "\n\n".join([
        f"Issue: {i['extracted_issue']}\n"
        f"Domain: {i['domain']} | Segment: {i['segment']} | "
        f"Mentions: {i['mentions']} | Sources: {i['sources']}\n"
        f"Solution: {i.get('solution', 'Escalate to engineering')}"
        for i in grouped_items
    ])

    resp = _client.messages.create(
        model="claude-sonnet-4-6", max_tokens=8096,
        system="""You are a technical writer producing issue reports for Product Owners.
Write a professional markdown report with:
1. Header: date, source, total issues, period
2. Summary table: Domain | Issue Count | Top Issue | Severity (🔴5+ 🟡2-4 🟢1)
3. Per-domain section with table: # | Issue | Description | Domain | Segment | Sources | Mentions | Suggested Approach
Do not invent issues. Only report what is in the data provided.""",
        messages=[{"role": "user", "content":
            f"Generate the {date} {source_label} report.\n\n{summary}"}]
    )
    return resp.content[0].text

def save_report(content: str, filename: str) -> str:
    import os
    date   = datetime.now().strftime("%Y-%m-%d")
    folder = f"output/{date}"
    os.makedirs(folder, exist_ok=True)
    path = f"{folder}/{filename}"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
```

---

### Step 11 — Guardrails
File: `report/guardrails.py`

```python
def validate(report: str, grouped_items: list[dict]) -> dict:
    errors, warnings = [], []

    if "| # | Issue |" not in report:
        errors.append("Missing issue table")

    for domain in {i["domain"] for i in grouped_items}:
        if domain not in report:
            errors.append(f"Domain '{domain}' missing from report")

    if len(report) < 400:
        errors.append("Report too short — may be incomplete")

    return {"passed": not errors, "errors": errors, "warnings": warnings}

def generate_with_retry(grouped_items, source_label, max_retries=3):
    from report.generator import generate_report
    for attempt in range(max_retries):
        report = generate_report(grouped_items, source_label)
        result = validate(report, grouped_items)
        if result["passed"]:
            return report
        print(f"  Retry {attempt+1}: {result['errors']}")
    raise RuntimeError("Report failed guardrails after max retries")
```

**Test — run end to end with mock data:**
```python
# Quick integration test for Phase 5
mock_grouped = [{
    "extracted_issue": "Visa card top-up failing with E5001",
    "domain": "Payment", "segment": "Top-up",
    "mentions": 3, "sources": "Facebook, Jira",
    "solution": "Increase 3DS timeout to 30s."
}]
from report.guardrails import generate_with_retry
report = generate_with_retry(mock_grouped, "Test")
print(report[:500])
```

---

## Phase 6 — Wire the Jobs (Day 3–4)

### Step 12 — Jira Job
File: `jobs/jira_job.py`

```python
from mock_data import get_mock_jira        # swap for real connector later
from processors.preprocessor import preprocess
from processors.issue_extractor import extract_issue
from processors.classifier import classify_domain, classify_segment
from knowledge_base.search import search_knowledge_base
from processors.grouper import group_similar
from report.guardrails import generate_with_retry
from report.generator import save_report

def run_jira_job(days_back: int = 1):
    print("=== JOB 1: Jira ===")
    raw      = get_mock_jira()                    # ← swap to fetch_jira() later
    cleaned  = preprocess(raw)
    print(f"  {len(raw)} tickets → {len(cleaned)} after preprocess")

    enriched = []
    for item in cleaned:
        try:
            issue    = extract_issue(item["text"])
            domain   = classify_domain(issue)
            segment  = classify_segment(issue, domain)
            solution = search_knowledge_base(issue)
            enriched.append({**item, "extracted_issue": issue,
                             "domain": domain, "segment": segment,
                             "solution": solution})
        except Exception as e:
            print(f"  ⚠️  Skipped {item['id']}: {e}")

    grouped = group_similar(enriched)
    print(f"  {len(enriched)} items → {len(grouped)} groups")

    report = generate_with_retry(grouped, "Jira")
    path   = save_report(report, "jira_report.md")
    print(f"  ✅ Saved: {path}")
```

**Test:** `python -c "from jobs.jira_job import run_jira_job; run_jira_job()"`
→ Should produce `output/{date}/jira_report.md`

---

### Step 13 — Social Job
File: `jobs/social_job.py`

```python
from concurrent.futures import ThreadPoolExecutor
from mock_data import get_mock_social
from processors.preprocessor import preprocess
from processors.sentiment import is_negative
from processors.image_analyzer import load_sample_images, analyze_image
from processors.issue_extractor import extract_issue
from processors.classifier import classify_domain, classify_segment
from knowledge_base.search import search_knowledge_base
from processors.grouper import group_similar
from report.guardrails import generate_with_retry
from report.generator import save_report

_samples = load_sample_images()   # load once at import time

def run_social_job(days_back: int = 1):
    print("=== JOB 2: Social Media ===")
    raw     = get_mock_social()                   # ← swap to real connectors later
    cleaned = preprocess(raw)

    negative = [p for p in cleaned if is_negative(p["text"])]
    print(f"  {len(raw)} posts → {len(negative)} negative after filter")

    enriched = []
    for post in negative:
        try:
            img_desc = None
            if post.get("images"):
                result   = analyze_image(post["images"][0], _samples)
                img_desc = result.get("issue_description")

            issue    = extract_issue(post["text"], img_desc or "")
            domain   = classify_domain(issue)
            segment  = classify_segment(issue, domain)
            solution = search_knowledge_base(issue)
            enriched.append({**post, "image_analysis": img_desc,
                             "extracted_issue": issue, "domain": domain,
                             "segment": segment, "solution": solution})
        except Exception as e:
            print(f"  ⚠️  Skipped {post['id']}: {e}")

    grouped = group_similar(enriched)
    print(f"  {len(enriched)} items → {len(grouped)} groups")

    report = generate_with_retry(grouped, "Social Media")
    path   = save_report(report, "social_report.md")
    print(f"  ✅ Saved: {path}")
```

---

## Phase 7 — Trigger Layer + UI (Day 4)

### Step 14 — FastAPI + Scheduler
File: `main.py`

```python
from fastapi import FastAPI, BackgroundTasks
from apscheduler.schedulers.background import BackgroundScheduler
from jobs.jira_job import run_jira_job
from jobs.social_job import run_social_job

app       = FastAPI(title="Data Analytics Agent")
scheduler = BackgroundScheduler()
status    = {}

def _run_jira():
    status["jira"] = "running"
    try:    run_jira_job();       status["jira"] = "done"
    except Exception as e: status["jira"] = f"error: {e}"

def _run_social():
    status["social"] = "running"
    try:    run_social_job();     status["social"] = "done"
    except Exception as e: status["social"] = f"error: {e}"

@app.on_event("startup")
def start_scheduler():
    scheduler.add_job(_run_jira,   "cron", hour=8, minute=0)
    scheduler.add_job(_run_social, "cron", hour=8, minute=10)
    scheduler.start()

@app.post("/run/jira")
def trigger_jira(bg: BackgroundTasks):
    bg.add_task(_run_jira);   return {"status": "started", "job": "jira"}

@app.post("/run/social")
def trigger_social(bg: BackgroundTasks):
    bg.add_task(_run_social); return {"status": "started", "job": "social"}

@app.post("/run/all")
def trigger_all(bg: BackgroundTasks):
    bg.add_task(_run_jira); bg.add_task(_run_social)
    return {"status": "started", "job": "all"}

@app.get("/status")
def get_status(): return status
```

---

### Step 15 — Streamlit Dashboard
File: `dashboard.py`

```python
import streamlit as st, glob, requests, os

st.set_page_config(page_title="Issue Report Dashboard", layout="wide")
st.title("Daily Issue Report Dashboard")

API = "http://localhost:8000"

# Trigger buttons
col1, col2, col3 = st.columns(3)
if col1.button("▶ Run Jira Job"):
    requests.post(f"{API}/run/jira"); st.success("Jira job started!")
if col2.button("▶ Run Social Job"):
    requests.post(f"{API}/run/social"); st.success("Social job started!")
if col3.button("▶ Run All"):
    requests.post(f"{API}/run/all"); st.success("Both jobs started!")

# Job status
try:
    s = requests.get(f"{API}/status", timeout=2).json()
    st.info(f"Jira: {s.get('jira','—')}   |   Social: {s.get('social','—')}")
except: pass

st.divider()

# Show reports
reports = sorted(glob.glob("output/**/*.md", recursive=True), reverse=True)
if not reports:
    st.warning("No reports yet. Run a job first.")
else:
    selected = st.selectbox("Select report", reports)
    with open(selected, encoding="utf-8") as f:
        st.markdown(f.read())
```

**Run:**
```bash
# Terminal 1: API server
uvicorn main:app --reload

# Terminal 2: Dashboard
streamlit run dashboard.py
```

---

## Phase 8 — Real API Connectors (Day 4–5)

Only after the full pipeline works on mock data. Swap one line in each job file.

### Step 16 — Jira Connector
File: `connectors/jira.py`

```python
from jira import JIRA
from datetime import datetime, timedelta
from config import JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN

_jira = JIRA(server=JIRA_URL, basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN))

def fetch_jira_tickets(days_back: int = 1) -> list[dict]:
    since  = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    issues = _jira.search_issues(
        f'project = ZLP AND created >= "{since}" ORDER BY created DESC',
        maxResults=200
    )
    return [{
        "id": i.key, "source": "jira",
        "text": f"{i.fields.summary}\n{i.fields.description or ''}",
        "images": [], "timestamp": i.fields.created,
    } for i in issues]
```

### Step 17 — Social Connectors
Files: `connectors/facebook.py`, `connectors/threads.py`
(See [[Projects/Data Sources]] for full code)

**To swap in `jira_job.py`:**
```python
# Replace:  from mock_data import get_mock_jira
# With:     from connectors.jira import fetch_jira_tickets
# And:      raw = fetch_jira_tickets(days_back)
```

---

## Complete Timeline

| Day | Phase | Steps | Deliverable |
|-----|-------|-------|------------|
| 1 AM | Phase 0 | — | KB docs, sample images, domain list, .env |
| 1 PM | Phase 1 | 1–2 | `config.py`, `mock_data.py` — project runs |
| 2 AM | Phase 2 | 3–4 | `preprocessor.py`, `sentiment.py` — tested |
| 2 PM | Phase 2 | 5–6 | `issue_extractor.py`, `classifier.py` — tested |
| 2 PM | Phase 3 | 7 | `knowledge_base/` indexed and searchable |
| 3 AM | Phase 4 | 8–9 | `image_analyzer.py`, `grouper.py` — tested |
| 3 PM | Phase 5 | 10–11 | Report generates from mock data |
| 4 AM | Phase 6 | 12 | Jira job end-to-end — `jira_report.md` produced |
| 4 PM | Phase 6 | 13 | Social job end-to-end — `social_report.md` produced |
| 4 PM | Phase 7 | 14–15 | FastAPI + Streamlit — full demo works |
| 5 | Phase 8 | 16–17 | Real Jira API wired (Facebook/Threads if time) |

---

## Team Split (4 Members)

| Member | Owns | Steps |
|--------|------|-------|
| A | Preprocessor + Sentiment + Image Analyzer | 3, 4, 8 |
| B | Issue Extractor + Classifier + Jira Job | 5, 6, 12 |
| C | Knowledge Base + Grouper + Social Job | 7, 9, 13 |
| D | Report Generator + Guardrails + FastAPI + Streamlit | 10, 11, 14, 15 |

Steps 1, 2 = everyone does together (30 min setup).
Steps 16, 17 = Member A or B on Day 5.

---

## Related Notes

- [[Projects/Architecture]] — full system diagrams
- [[Projects/Architecture Review]] — gaps and fixes
- [[Projects/Pipeline Deep Dive]] — why each technique exists
- [[Projects/Data Sources]] — connector details
- [[Projects/Report Format]] — expected output format
