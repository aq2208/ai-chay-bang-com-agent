# LLM as a Processing Step

#concept #architecture

> [!note] In the project, every LLM processing step uses the single model **`google/gemma-4-31b-it` via
> AgentBase MaaS** (the fast/smart tiering collapses to one model). Model IDs in examples below are
> illustrative. Canonical design: [[Projects/00 - Project Home]].

---

## The Core Idea

You don't feed all raw data into one giant LLM call.
You use the LLM as a **focused processor at specific steps** in a pipeline.

```
Raw data → [Code filters] → [LLM step] → [LLM step] → [LLM report]
```

Each LLM call has exactly **one job**. Small, specific, reliable.

---

## The Pipeline Pattern

```
FETCH           → pure code (HTTP, API calls)
PRE-FILTER      → pure code (keyword match, date range, dedup)
SENTIMENT       → LLM call per item  ("is this negative?")
IMAGE ANALYSIS  → LLM call per item  ("what issue is shown?")
CLASSIFY        → LLM call per item  ("what domain/segment?")
RAG LOOKUP      → vector search, not LLM  ("what's the solution?")
REPORT WRITE    → one LLM call over structured summaries
```

---

## Why Not One Big LLM Call?

```python
# ❌ Tempting but wrong
prompt = "Here are 200 social media posts, analyze them all: " + str(raw_posts)
llm.call(prompt)
```

Problems:
- **Context limit** — 200 posts might exceed the context window
- **Unfocused** — LLM tries to do too many things at once, quality drops
- **Expensive** — you pay for all tokens whether or not they're relevant
- **Unreliable output** — hard to parse one massive unstructured response
- **Can't retry one step** — if classification fails, you redo everything

---

## The Right Pattern

```python
# ✅ Many small, focused LLM calls
for post in posts:
    # Each call has ONE job, ONE clear output
    sentiment = is_negative(post["text"])       # returns True/False
    domain    = classify_domain(post["text"])   # returns "Payment"
    segment   = classify_segment(post["text"])  # returns "Top-up"
    solution  = search_knowledge_base(issue)    # RAG, not even LLM

# One final call — but with STRUCTURED data, not raw posts
report = generate_report(enriched_items)
```

---

## What You Feed Into Each LLM Call

| Step | Input | Output |
|------|-------|--------|
| Sentiment filter | Raw post text | `"NEGATIVE"` / `"POSITIVE"` |
| Image analysis | Post image + sample images | Issue description string |
| Domain classify | Post text + image description | `"Payment"` |
| Segment classify | Post text + domain | `"Top-up"` |
| Issue extraction | Post text + image description | `"Visa top-up fails with E5001"` |
| Report writing | List of structured dicts | Full markdown report |

---

## What the Final LLM Call Receives

By the time you generate the report, each item has been cleaned and structured.
You pass **summaries**, not raw text:

```python
# Raw post (noisy, long, in Vietnamese):
"Zalopay bị lỗi rồi! Không nạp tiền được suốt 2 tiếng!! 😡😡 [image attached]"

# After processing (clean, structured):
{
    "extracted_issue": "Top-up failure — Visa card",
    "domain":   "Payment",
    "segment":  "Top-up",
    "sources":  ["Facebook", "Jira"],
    "mentions": 6,
    "solution": "Increase retry limit to 3. See KB-42."
}
```

The report-writing LLM reads clean data → writes a clean report.
Much cheaper, faster, and more reliable than feeding raw posts.

---

## Do LLM Calls Per Item Scale?

For a daily batch job:

- 60 items × 3 LLM calls each = 180 calls
- Each call: ~200 tokens in + ~50 tokens out = 250 tokens
- Total: 180 × 250 = 45,000 tokens
- Cost with Claude Haiku: ~$0.01 per run ✅

Use **Haiku** for classification/sentiment (fast, cheap).
Use **Sonnet** only for image analysis and report writing.

---

## Parallelizing LLM Calls

You can run LLM calls for multiple items at the same time:

```python
from concurrent.futures import ThreadPoolExecutor

def enrich_item(item):
    item["sentiment"] = is_negative(item["text"])
    item["domain"]    = classify_domain(item["text"])
    item["solution"]  = search_knowledge_base(item["text"])
    return item

# Process 10 items at once instead of one by one
with ThreadPoolExecutor(max_workers=10) as ex:
    enriched = list(ex.map(enrich_item, filtered_posts))
```

This turns a 60-second sequential run into a 6-second parallel run.

---

## Summary

| Principle | Why |
|-----------|-----|
| One LLM call = one job | Focused → reliable output |
| Pre-filter with code first | LLM time is expensive; drop junk with cheap code |
| Feed structured data to report LLM | Better quality, lower cost than raw text |
| Use Haiku for classification | 10x cheaper than Sonnet for simple yes/no tasks |
| Parallelize where possible | Much faster wall-clock time |

---

## Related Notes

- [[Projects/Architecture]] — where each LLM call fits in the pipeline
- [[Concepts/Agent Loop - ReAct Pattern]] — when you DO want a loop instead
- [[Concepts/LLM API Basics]] — how to make individual LLM calls
- [[Concepts/Prompt Engineering]] — how to write focused single-job prompts
