# Pipeline Deep Dive — How Every Technique Fits

#project #concept

> [!info] Canonical design: **[[Projects/00 - Project Home]]**. Updated 2026-06-11: every LLM call uses
> **`google/gemma-4-31b-it` via AgentBase MaaS** (the `claude-*` model IDs in code samples below are
> historical — the logic is unchanged). Classification is now **RAG-grounded** (Stage 6 retrieves
> taxonomy/known-issue examples), and a final step indexes issues into the **`issues`** collection for
> the **agentic Q&A** endpoint.

---

## How to Read This Note

We trace **one real item** through the entire pipeline from raw input to final report row.
For each stage: what it is, why we need it, how we apply it, input → output, and what breaks without it.

---

## Where Embedding Fits — Common Misconception

> "We should apply embedding right after tokenization."

This comes from **classical ML pipelines** where the model reads vectors:
```
Classical ML:  Text → Tokenize → Embed → feed vector into model
```

Your pipeline is different. The LLM reads **text**, not vectors. Embedding serves a different role here — it powers **search** (RAG) and **clustering** (grouping), both of which happen AFTER issue extraction:

```
Your pipeline:
  Stage 1 — Preprocess    → clean text (LLM reads this)
  Stage 5 — Issue extract → "Visa top-up failing with E5001"
                                      ↓
  Stage 7 — RAG           → EMBED extracted issue → search ChromaDB → retrieve text
  Stage 8 — Grouping      → EMBED all extracted issues → cluster similar ones
```

**Why embed the extracted issue, not the raw text?**
```
❌ embed("Zalopay bị lỗi rồi! 😡 Không nạp tiền được bằng Visa suốt 2 tiếng!")
   → noisy vector, mixes language + emotion + product name + feature

✅ embed("Visa card top-up failing with error E5001")
   → precise vector, represents the technical problem cleanly
```

Better input → better vector → better RAG matches → better semantic grouping.

---

**Our running example — a Facebook post:**
```json
{
  "id": "FB-2001",
  "source": "facebook",
  "text": "Zalopay bị lỗi rồi!!!! 😡😡 Không nạp tiền được bằng Visa suốt 2 tiếng!! http://fb.com/photo/123",
  "images": ["https://fb.com/photo/screenshot.jpg"],
  "timestamp": "2026-06-10T08:30:00"
}
```

---

## Stage 0 — Data Fetching

**What it is:** Plain HTTP API calls to Jira, Facebook, and Threads.
No intelligence here — just pull raw data.

**Why:** You need data to process. No LLM, no ML — just network calls.

**How:**
```python
# Facebook keyword search
posts = requests.get("https://graph.facebook.com/v19.0/PAGE_ID/feed", params={
    "access_token": TOKEN,
    "fields": "id,message,attachments,created_time",
}).json()
```

**Output after this stage:**
```json
{
  "id": "FB-2001",
  "source": "facebook",
  "text": "Zalopay bị lỗi rồi!!!! 😡😡 Không nạp tiền được bằng Visa suốt 2 tiếng!! http://fb.com/photo/123",
  "images": ["https://fb.com/photo/screenshot.jpg"],
  "timestamp": "2026-06-10T08:30:00"
}
```

**What breaks without it:** Nothing to process.

---

## Stage 1 — Tokenization & Text Preprocessing

**What it is:** Cleaning raw text — removing noise, normalizing format.
"Tokenization" in the classical NLP sense means splitting text into units (words, subwords). For your pipeline, you don't need manual tokenization — embedding models do it internally. What you DO need is cleaning.

**Why:** Raw social media text is full of noise: emoji, URLs, excessive punctuation, hashtags, @mentions. These add no meaning but confuse ML models and increase token cost when fed to LLMs.

**How:**
```python
import re

def clean_text(text: str) -> str:
    text = re.sub(r'http\S+', '', text)        # remove URLs
    text = re.sub(r'#\w+', '', text)            # remove #hashtags
    text = re.sub(r'@\w+', '', text)            # remove @mentions
    text = re.sub(r'[^\w\s-￿]', ' ', text)  # remove emoji, keep Vietnamese
    text = re.sub(r'[!?]{2,}', '!', text)      # normalize !!! → !
    text = re.sub(r'\s+', ' ', text).strip()   # collapse whitespace
    return text

def is_meaningful(text: str, min_words: int = 4) -> bool:
    return len(text.split()) >= min_words
```

**Input:**
```
"Zalopay bị lỗi rồi!!!! 😡😡 Không nạp tiền được bằng Visa suốt 2 tiếng!! http://fb.com/photo/123"
```

**Output after this stage:**
```
"Zalopay bị lỗi rồi! Không nạp tiền được bằng Visa suốt 2 tiếng!"
```

**What improves:**
- Sentiment model accuracy ↑ (emoji confuse models)
- Embedding quality ↑ (URLs are pure noise in vector space)
- LLM token cost ↓ (shorter text = fewer tokens)
- Deduplication accuracy ↑ (two identical complaints with different emoji won't look different)

**What breaks without it:** Two posts "Lỗi!!! 😡" and "Lỗi! 😭" would embed as different texts. Your deduplication and grouping fails. LLM wastes tokens on emoji characters.

---

## Stage 2 — Keyword Filter (Social Media Only)

**What it is:** Simple string matching — keep only posts that mention your product by name.

**Why:** You searched Facebook by keyword, but the results still include noise — posts that mention "zalopay" in passing, unrelated context, etc. A quick keyword match catches obviously irrelevant posts before the expensive ML/LLM steps.

**How:**
```python
KEYWORDS = ["zalopay", "ví zalopay", "nạp tiền", "thanh toán zalo"]

def mentions_product(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in KEYWORDS)
```

**Input:** Cleaned text  
**Output:** Boolean — keep or drop

**What improves:** Drops irrelevant posts before sentiment analysis. Saves ML model inference time.

**What breaks without it:** You waste sentiment analysis compute on posts that have nothing to do with your product.

---

## Stage 3 — Sentiment Analysis

**What it is:** A pre-trained ML model (not LLM) that classifies text as POSITIVE, NEGATIVE, or NEUTRAL by detecting emotional tone.

**Why:** You only want negative posts — complaints, problems, frustrations. Positive posts ("I love ZaloPay!") and neutral posts ("Does ZaloPay support ATM?") should be dropped. Using an ML model instead of an LLM for this is:
- 100x faster (milliseconds vs seconds)
- Free (runs locally, no API cost)
- Good enough for a binary filter

**How:**
```python
from transformers import pipeline

# Load once at startup (not per-post)
sentiment_model = pipeline(
    "text-classification",
    model="wonrax/phobert-base-vietnamese-sentiment"
    # Labels: NEG, POS, NEU
)

def is_negative(text: str) -> tuple[bool, float]:
    result = sentiment_model(text[:512])[0]   # model has 512 token limit
    label = result["label"]    # "NEG", "POS", or "NEU"
    score = result["score"]    # confidence 0.0 → 1.0

    if label == "NEG" and score >= 0.75:
        return True, score     # clearly negative
    if label == "POS" and score >= 0.75:
        return False, score    # clearly positive
    # Borderline → ask LLM as tiebreaker
    return _llm_sentiment_check(text), score

def _llm_sentiment_check(text: str) -> bool:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=5,
        system="Is this text expressing a complaint or problem? Reply YES or NO only.",
        messages=[{"role": "user", "content": text}]
    )
    return "YES" in response.content[0].text.upper()
```

**Input:**
```
"Zalopay bị lỗi rồi! Không nạp tiền được bằng Visa suốt 2 tiếng!"
```

**Output after this stage:**
```json
{
  "sentiment_label": "NEG",
  "sentiment_score": 0.94,
  "is_negative": true
}
```

Posts where `is_negative = false` are **dropped here**. They never reach the LLM.

**What improves:** Eliminates positive/neutral posts (roughly 60% of raw volume). Every step after this runs on ~40% of the original data. Reduces LLM API cost dramatically.

**What breaks without it:** PO receives a report full of praise and irrelevant posts mixed with real complaints.

---

## Stage 4 — Image Analysis (Social Media Only)

**What it is:** Claude Sonnet reads the screenshot image + your team's sample images and describes what issue is shown.

**Why:** Users frequently post screenshots to explain their problem. A post saying "bị lỗi" (got an error) with a screenshot of error code E5001 contains critical information only visible in the image. Text-only processing would miss this entirely.

**Why Claude instead of a dedicated vision model:** Claude Sonnet natively understands images. It can also reason — comparing the user's screenshot against your sample images and identifying which known issue it matches. A simpler vision model just describes the image; Claude connects it to your domain knowledge.

**How:**
```python
import base64, requests as req

def analyze_post_image(image_url: str, sample_images: list[dict]) -> dict:
    content = []

    # 1. Add the user's screenshot
    content.append({
        "type": "image",
        "source": {"type": "url", "url": image_url}
    })
    content.append({
        "type": "text",
        "text": "This is a screenshot posted by a user reporting a ZaloPay problem.\n\nCompare it with these known issue samples:"
    })

    # 2. Add each sample reference image
    for sample in sample_images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": sample["data"]}
        })
        content.append({
            "type": "text",
            "text": f"Sample: {sample['label']} (Domain: {sample['domain']})"
        })

    # 3. Ask for structured analysis
    content.append({
        "type": "text",
        "text": """Analyze the user's screenshot. Answer in JSON:
{
  "issue_description": "what issue the user is experiencing",
  "matched_sample": "which sample it most resembles, or 'none'",
  "domain": "which domain (Payment/QR Code/Account/App Performance/Other)",
  "confidence": "high/medium/low",
  "visible_error_code": "any error code visible in the image, or null"
}"""
    })

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": content}]
    )

    import json
    text = response.content[0].text
    return json.loads(text[text.find("{"):text.rfind("}")+1])
```

**Input:** Image URL + list of sample reference images  
**Output after this stage:**
```json
{
  "image_description": "Payment screen showing error code E5001 in red after entering Visa card details",
  "matched_sample": "E5001 payment declined",
  "domain": "Payment",
  "confidence": "high",
  "visible_error_code": "E5001"
}
```

This output is **combined with the post text** for the next stages.

**What improves:** Extracts information invisible to text-only processing. A post that says only "bị lỗi 😡" but has a screenshot becomes fully understood.

**What breaks without it:** ~40% of social posts contain images with critical diagnostic information that is completely lost.

---

## Stage 5 — Issue Extraction

**What it is:** A focused LLM call (Haiku) that reads the post text + image description and produces a clean, structured issue statement.

**Why:** Raw user text is messy, emotional, and unpredictable. "Zalopay bị lỗi rồi! Không nạp tiền được bằng Visa suốt 2 tiếng!!" needs to become "Visa card top-up failure (error E5001)" — a clean, consistent statement usable for grouping, RAG search, and the report.

**How:**
```python
def extract_issue(text: str, image_description: str = "") -> str:
    combined = text
    if image_description:
        combined += f"\n[Image shows: {image_description}]"

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",   # cheap, fast, sufficient
        max_tokens=60,
        system="""Extract the core technical issue from this user complaint.
Output: one clear English sentence, 8-15 words.
Focus on: what failed, which feature, any error code visible.
Do not include emotional language.""",
        messages=[{"role": "user", "content": combined}]
    )
    return response.content[0].text.strip()
```

**Input:**
```
Text: "Zalopay bị lỗi rồi! Không nạp tiền được bằng Visa suốt 2 tiếng!"
Image: "Payment screen showing error E5001 after entering Visa card details"
```

**Output after this stage:**
```
"Visa card top-up failing with error E5001 on payment screen"
```

**What improves:** Normalizes messy user language into a consistent, searchable technical statement. This clean statement is what gets embedded for RAG search and semantic grouping. Two posts saying the same thing in different words both extract to the same (or very similar) issue statement → groups correctly.

**What breaks without it:** RAG search would get "Zalopay bị lỗi 😡" as a query, which is a poor embedding. Semantic grouping would fail to cluster identical issues together.

---

## Stage 6 — Domain & Segment Classification

**What it is:** Two focused Haiku calls that assign a category (domain) and subcategory (segment) to each issue.

**Why:** The PO needs issues organized by product area, not as a flat list. "Visa top-up failing" → Payment / Top-up. "QR not scanning" → QR Code / Merchant. Without this, you can't produce domain-grouped reports.

**How:**
```python
DOMAINS   = ["Payment", "QR Code", "Account", "App Performance", "Merchant", "Other"]
SEGMENTS  = {
    "Payment":   ["Top-up", "Transfer", "Withdrawal", "Billing"],
    "QR Code":   ["Payment", "Generation", "Merchant"],
    "Account":   ["Login", "OTP", "Registration", "Profile"],
    "App Performance": ["Crash", "Loading", "UI Bug"],
    "Merchant":  ["POS", "Settlement", "Onboarding"],
    "Other":     ["General"],
}

def classify_domain(issue: str, text: str) -> str:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        system=f"Classify into exactly one: {', '.join(DOMAINS)}. Reply with the domain name only.",
        messages=[{"role": "user", "content": f"Issue: {issue}\nContext: {text[:200]}"}]
    )
    label = response.content[0].text.strip()
    return label if label in DOMAINS else "Other"

def classify_segment(issue: str, domain: str) -> str:
    options = SEGMENTS.get(domain, ["General"])
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        system=f"Classify into exactly one: {', '.join(options)}. Reply with the segment name only.",
        messages=[{"role": "user", "content": issue}]
    )
    label = response.content[0].text.strip()
    return label if label in options else options[0]
```

**Input:**
```
Issue: "Visa card top-up failing with error E5001 on payment screen"
```

**Output after this stage:**
```json
{
  "domain":  "Payment",
  "segment": "Top-up"
}
```

**What improves:** Enables domain-grouped reports. The PO gets "Payment: 9 issues" instead of a flat list of 27 items.

**What breaks without it:** All issues in one unstructured list. PO cannot quickly find issues in their product area.

---

## Stage 7 — Embeddings + RAG

**What it is:** Two steps that work together:
1. **Embed** the extracted issue into a vector (numbers representing its meaning)
2. **Search** ChromaDB for the most similar KB doc vector → **retrieve** that doc's text

**Why:** Your team has written solution guides ("how to fix E5001", "how to handle QR scan failure"). The LLM doesn't know what's in those docs unless you find the relevant one and inject it into the prompt. RAG is how you do that retrieval — by meaning, not keyword.

**Remember:** You don't feed vectors to the LLM. You use vectors to *find* the right doc, then feed the *text* of that doc to the LLM.

**How:**
```python
from sentence_transformers import SentenceTransformer
import chromadb

# Load once at startup
embedder    = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
db          = chromadb.PersistentClient(path="./chroma_db")
kb_collection = db.get_or_create_collection("knowledge_base")

# --- INDEX KB DOCS (do once, at setup) ---
def index_knowledge_base(docs_folder: str):
    import os
    for filename in os.listdir(docs_folder):
        with open(f"{docs_folder}/{filename}") as f:
            text = f.read()
        vector = embedder.encode(text).tolist()
        kb_collection.add(
            documents=[text],
            embeddings=[vector],
            ids=[filename]
        )

# --- SEARCH AT RUNTIME (called per issue) ---
def search_knowledge_base(issue: str, n_results: int = 2) -> str:
    query_vector = embedder.encode(issue).tolist()
    results = kb_collection.query(
        query_embeddings=[query_vector],
        n_results=n_results
    )
    docs = results["documents"][0]          # list of matching doc texts
    scores = results["distances"][0]        # similarity scores

    # Only use results above similarity threshold
    relevant = [doc for doc, score in zip(docs, scores) if score < 0.5]
    if not relevant:
        return "No known solution found. Escalate to engineering team."

    return "\n---\n".join(relevant)         # return text, not vectors
```

**Input:**
```
Issue: "Visa card top-up failing with error E5001 on payment screen"
```

**What happens internally:**
```
1. embed("Visa card top-up failing with error E5001")
   → [0.23, -0.41, 0.88, ...] (384 numbers)

2. Search ChromaDB for closest stored vectors
   → finds "payment_e5001.md" (similarity: 0.91)
   → finds "payment_gateway_timeout.md" (similarity: 0.78)

3. Return the TEXT of those docs (not the vectors)
```

**Output after this stage:**
```
"E5001 — Payment Gateway Timeout
Cause: 3DS authentication timeout on Visa cards during high traffic.
Fix: Increase 3DS timeout from 10s to 30s. Add retry button (max 3).
Escalate to: payment gateway provider if persists beyond 24h."
```

**What improves:** The LLM report writer receives the relevant solution text directly in its prompt. Without this, the LLM would have to guess solutions from its training data — which may be wrong, outdated, or not specific to your system.

**What breaks without it:** LLM invents generic solutions ("contact support") instead of specific, accurate fixes.

---

## Stage 8 — Semantic Grouping

**What it is:** Using embeddings + cosine similarity to cluster items that describe the same issue, even if worded differently. Multiple posts → one row in the report with a `mentions` count.

**Why:** Without grouping, 7 Facebook posts all complaining about Visa top-up would produce 7 separate rows in the report. The PO would see them as 7 different issues. With grouping, they become 1 row with `mentions = 7, sources = FB(5), Jira(2)` — which correctly signals HIGH priority.

**How:**
```python
import numpy as np

def cosine_similarity(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def group_by_similarity(items: list[dict], threshold: float = 0.82) -> list[dict]:
    """
    Groups items with similar extracted_issue into clusters.
    Returns one representative item per cluster with merged metadata.
    """
    if not items:
        return []

    # Embed all extracted issues
    issues  = [i["extracted_issue"] for i in items]
    vectors = embedder.encode(issues)

    used     = set()
    groups   = []

    for i, vec_i in enumerate(vectors):
        if i in used:
            continue

        cluster = [items[i]]
        used.add(i)

        for j, vec_j in enumerate(vectors):
            if j in used:
                continue
            if cosine_similarity(vec_i, vec_j) >= threshold:
                cluster.append(items[j])
                used.add(j)

        # Merge cluster into one representative item
        all_sources  = list({item["source"] for item in cluster})
        all_origins  = list({item.get("origin", item["source"]) for item in cluster})
        representative = cluster[0].copy()   # use first item as base
        representative["mentions"] = len(cluster)
        representative["sources"]  = ", ".join(sorted(all_sources))
        representative["raw_items"] = cluster  # keep originals for appendix

        groups.append(representative)

    # Sort by mention count descending (most reported first)
    return sorted(groups, key=lambda x: x["mentions"], reverse=True)
```

**Input:** 7 separate enriched items all about Visa top-up failing

**Output after this stage:**
```json
{
  "extracted_issue": "Visa card top-up failing with error E5001",
  "domain": "Payment",
  "segment": "Top-up",
  "mentions": 7,
  "sources": "Facebook, Jira",
  "solution": "E5001 — increase 3DS timeout to 30s..."
}
```

7 items → 1 grouped item with `mentions: 7`.

**What improves:** Report accurately reflects issue frequency and severity. Mention count drives the `Severity` column. PO can prioritize by `mentions` instead of guessing.

**What breaks without it:** 7 separate rows for the same issue. PO misreads them as 7 different problems. Priority is wrong. Report is cluttered.

---

## Stage 9 — LLM Report Generation

**What it is:** A single Claude Sonnet call that reads all grouped, structured items and writes the final table report.

**Why Sonnet here (not Haiku):** This requires real writing quality — synthesizing multiple inputs into a coherent, professional report. Haiku would produce lower quality prose and sometimes miss nuance.

**Why only one call:** By now each item is fully enriched (issue, domain, segment, mentions, solution). The LLM isn't doing any analysis here — it's just formatting known data into a readable table. One call is sufficient.

**What the LLM receives (NOT raw posts):**
```python
# Items passed to report LLM — clean structured data
items_text = """
Issue: Visa card top-up failing with error E5001
Domain: Payment | Segment: Top-up | Mentions: 7 | Sources: Facebook, Jira
Solution hint: Increase 3DS timeout to 30s. Add retry button.

Issue: QR code scan failure at merchants
Domain: QR Code | Segment: Merchant | Mentions: 3 | Sources: Facebook, Jira
Solution hint: Check merchant terminal firmware v2.1.3 compatibility.
"""
```

**How:**
```python
def generate_report(grouped_items: list[dict], date: str, source_label: str) -> str:
    items_text = "\n\n".join([
        f"Issue: {item['extracted_issue']}\n"
        f"Domain: {item['domain']} | Segment: {item['segment']} | "
        f"Mentions: {item['mentions']} | Sources: {item['sources']}\n"
        f"Solution: {item['solution']}"
        for item in grouped_items
    ])

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8096,
        system="""You are a technical writer producing issue reports for Product Owners.
Write a professional markdown report with:
1. Header (date, totals, period)
2. Summary table: Domain | Issue Count | Top Issue | Severity (🔴🟡🟢 by mentions)
3. Per-domain table: # | Issue | Description | Domain | Segment | Sources | Mentions | Suggested Approach
4. Severity: 🔴 High = 5+ mentions, 🟡 Medium = 2-4, 🟢 Low = 1
Do not invent issues. Only report what is in the data provided.""",
        messages=[{
            "role": "user",
            "content": f"Generate the {date} {source_label} issue report.\n\n{items_text}"
        }]
    )
    return response.content[0].text
```

**Input:** Clean structured grouped items  
**Output:** Full formatted markdown table report (see [[Projects/Report Format]])

**What improves:** Transforms structured data into a readable, professional document that a PO can actually act on. Natural language descriptions, consistent format, severity indicators.

**What breaks without it:** You'd have to write a template engine manually — much harder than letting the LLM format it.

---

## Stage 10 — Guardrails

**What it is:** Validation code (NOT LLM) that checks the LLM's output before saving. If validation fails, it retries with correction hints.

**Why:** LLMs can:
- Miss a domain section entirely
- Report an issue that wasn't in the input data (hallucination)
- Return malformed markdown (table broken)
- Skip the Suggested Approach column

These are silent failures — the report looks fine but is wrong. Guardrails catch them.

**How:**
```python
from pydantic import BaseModel, validator
import json

def validate_report(report: str, grouped_items: list[dict]) -> dict:
    errors   = []
    warnings = []

    # Check 1: Table header exists
    if "| # | Issue |" not in report:
        errors.append("Report is missing the issue table header row")

    # Check 2: All domains present
    domains = set(item["domain"] for item in grouped_items)
    for domain in domains:
        if domain not in report:
            errors.append(f"Domain '{domain}' has issues but is missing from the report")

    # Check 3: No hallucinated issues
    known_issues = " ".join(i["extracted_issue"].lower() for i in grouped_items)
    # (simplified check — look for table rows with keywords not in source)
    for line in report.split("\n"):
        if line.startswith("| ") and "|" in line[2:]:
            row_text = line.lower()
            # If none of the known issue keywords appear in this row, flag it
            keywords_found = any(
                kw in row_text
                for item in grouped_items
                for kw in item["extracted_issue"].lower().split()[:3]
            )
            if not keywords_found and len(line) > 20:
                warnings.append(f"Possible hallucinated row: {line[:80]}")

    # Check 4: Minimum length
    if len(report) < 500:
        errors.append("Report is suspiciously short — may be incomplete")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }

def generate_report_with_retry(items, date, source_label, max_retries=3):
    for attempt in range(max_retries):
        report = generate_report(items, date, source_label)
        result = validate_report(report, items)

        if result["passed"]:
            if result["warnings"]:
                print(f"  ⚠️  Warnings: {result['warnings']}")
            return report

        print(f"  Attempt {attempt+1} failed: {result['errors']}")
        # Retry with the error as a correction hint
        items_text = "\n".join(result["errors"])
        # (pass correction_hint to generate_report on next attempt)

    raise RuntimeError("Report failed guardrails after max retries")
```

**Input:** LLM-generated report markdown  
**Output:** Validated report OR retry with corrections

**What improves:** Catches silent failures before the PO sees them. Ensures every domain is covered, no hallucinations, correct format.

**What breaks without it:** PO receives reports with missing sections, invented issues, or broken tables — and doesn't know.

---

## Full Pipeline: Input → Output at Each Stage

Using our example Facebook post:

```
Stage 0 — FETCH
Input:  Facebook API call
Output: { id: "FB-2001", text: "Zalopay bị lỗi rồi!!!! 😡😡 Không nạp...", images: [...] }

Stage 1 — PREPROCESS
Input:  "Zalopay bị lỗi rồi!!!! 😡😡 Không nạp tiền được bằng Visa suốt 2 tiếng!! http://..."
Output: "Zalopay bị lỗi rồi! Không nạp tiền được bằng Visa suốt 2 tiếng!"

Stage 2 — KEYWORD FILTER
Input:  cleaned text
Output: True (contains "zalopay", "nạp tiền") → keep

Stage 3 — SENTIMENT ANALYSIS
Input:  "Zalopay bị lỗi rồi! Không nạp tiền được bằng Visa suốt 2 tiếng!"
Output: { label: "NEG", score: 0.94, is_negative: true } → keep

Stage 4 — IMAGE ANALYSIS
Input:  screenshot URL + 8 sample images
Output: { issue_description: "Payment screen showing E5001 error after Visa card entry",
          domain: "Payment", confidence: "high", visible_error_code: "E5001" }

Stage 5 — ISSUE EXTRACTION
Input:  text + image description
Output: "Visa card top-up failing with error E5001 on payment screen"

Stage 6 — CLASSIFICATION
Input:  extracted issue
Output: { domain: "Payment", segment: "Top-up" }

Stage 7 — RAG LOOKUP
Input:  "Visa card top-up failing with error E5001"
Step a: embed → [0.23, -0.41, 0.88, ...]
Step b: search ChromaDB → finds "payment_e5001.md" (similarity 0.91)
Step c: retrieve text → "E5001 — Payment Gateway Timeout. Fix: increase 3DS timeout..."
Output: solution text string

Stage 8 — SEMANTIC GROUPING (with 6 other similar posts)
Input:  7 individual items all about Visa/E5001
Output: 1 grouped item { mentions: 7, sources: "Facebook, Jira", ... }

Stage 9 — LLM REPORT
Input:  all grouped items as structured text
Output: Full markdown report with tables

Stage 10 — GUARDRAILS
Input:  report markdown
Output: Validated report saved to output/2026-06-10/social_report.md
```

---

## Why Each Technique Is There — One-Line Summary

| Technique | One-Line Reason |
|-----------|----------------|
| Preprocessing | Cleans noise so every downstream step works better |
| Keyword filter | Drops irrelevant posts before touching ML/LLM |
| Sentiment analysis (ML) | Keeps only complaints, fast and free, before LLM budget is spent |
| Image analysis (LLM Vision) | Extracts issue info visible only in screenshots |
| Issue extraction (LLM) | Normalizes messy user language into clean searchable text |
| Classification (LLM) | Assigns domain/segment so reports can be organized by product area |
| Embedding | Converts text to numbers for meaning-based search and grouping |
| RAG | Retrieves your team's specific solutions from the knowledge base |
| Semantic grouping | Merges duplicate complaints so mention counts are accurate |
| LLM report | Formats structured data into readable professional markdown |
| Guardrails | Validates output so silent failures don't reach the PO |

---

## Related Notes

- [[Concepts/Tokenization & Text Preprocessing]]
- [[Concepts/Sentiment Analysis]]
- [[Concepts/Embeddings]]
- [[Concepts/RAG - Retrieval-Augmented Generation]]
- [[Concepts/LLM as a Processing Step]]
- [[Concepts/Guardrails]]
- [[Projects/Image Processing]]
- [[Projects/Architecture]]
- [[Projects/Architecture Review]]
