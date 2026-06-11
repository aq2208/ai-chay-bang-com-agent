# How to Test the Pipeline on Real Data (step by step)

This guide walks the **real pipeline on real data — no mocks**. Each step **saves its output to a
file**, and the next step **reads that file as its input** — exactly like the real pipeline, but paused
at every boundary so you can inspect what each stage produced.

> Focus: the **Threads (social) path**, which crawls real public data with no API tokens.
> Facebook needs real Page tokens; the **Jira connector currently hits a removed Atlassian API**
> (`/rest/api/2/search` → HTTP 410) and must be migrated to `/rest/api/3/search/jql` before real Jira
> testing — see "Known issues" at the bottom.

Intermediate artifacts go in `data/test/` (gitignored). Bronze crawl data goes in `data/raw/`.

```
crawl → data/raw/threads_*.jsonl        (Step 1: raw / bronze)
      → data/test/1_fetched.json        (Step 3: normalized)
      → data/test/2_clean.json          (Step 4: preprocessed)
      → data/test/3_negative.json       (Step 5: sentiment-filtered)
      → data/test/4_imaged.json         (Step 6: + image analysis)
      → data/test/5_extracted.json      (Step 7: + extracted_issue)
      → data/test/6_classified.json     (Step 8: + domain/segment)
      → data/test/7_grouped.json        (Step 9: merged + mentions)
      → output/<ts>_social_media.md     (Step 11: report)
      → ChromaDB 'issues' + Q&A         (Step 12)
```

> **Tip — two ways to run the steps:**
> - **File-based (this guide):** each step is a separate command that reads/writes `data/test/*.json`.
>   Best for inspecting boundaries; reloads ML models each run (slower).
> - **Interactive:** run `.venv/bin/python -i` once and paste each step's *core* lines, keeping the
>   `items` variable live between steps (models stay warm). Faster, but less isolation.

---

## Step 0 — Prerequisites

```bash
cd clawathon-aicbc-agent

# Agent deps (LLM client, ML, ChromaDB) — once
.venv/bin/pip install -r requirements.txt

# Crawler deps + browser (offline crawler only) — once
.venv/bin/pip install -r requirements-crawler.txt
.venv/bin/python -m playwright install chromium

# Provider LLM must be configured (set up via the agentbase skills):
bash ../.claude/skills/agentbase/scripts/check_credentials.sh llm   # expect OK
# .env should have: LLM_PROVIDER=openai, LLM_BASE_URL=<maas>/v1, LLM_API_KEY=<key>,
#                   MODEL_FAST=MODEL_SMART=google/gemma-4-31b-it

# Build the knowledge base + taxonomy indexes (needed for classify, KB, grouping) — once
.venv/bin/python knowledge_base/index.py
```

**Pass criteria:** `check_credentials.sh llm` prints OK; `index.py` prints "Indexed N solution chunks" + "Indexed M taxonomy chunks".

---

## Step 1 — Crawl real data → Bronze (`data/raw/threads_*.jsonl`)

**What it does:** Playwright opens Threads public search for each keyword in `config.KEYWORDS`, scrolls,
extracts posts, downloads attached images as base64, dedups by content hash, writes a bronze `.jsonl`.

```bash
.venv/bin/python crawlers/threads_crawler.py
```

To change keywords/scope, edit `config.KEYWORDS` / `config.DAYS_BACK`, or call from Python:
```bash
.venv/bin/python -c "from crawlers.threads_crawler import crawl; crawl(keywords=['zalopay','zalo pay'], scroll_times=4, max_age_hours=48)"
```

**Inspect:**
```bash
ls -lh data/raw/                          # newest threads_<ts>.jsonl
wc -l data/raw/threads_*.jsonl            # number of raw posts
.venv/bin/python -c "import json,glob; f=sorted(glob.glob('data/raw/threads_*.jsonl'))[-1]; rows=[json.loads(l) for l in open(f,encoding='utf-8')]; print('file:',f,'rows:',len(rows)); print(json.dumps({**rows[0],'images_base64':[f'<{len(rows[0][\"images_base64\"])} img>']}, ensure_ascii=False, indent=2)[:800])"
```

**Pass criteria:** a `data/raw/threads_<ts>.jsonl` exists with ≥1 row; each row has
`post_hash_id, platform, matched_keyword, author, content, posted_at, crawled_at, images_base64`.
If 0 rows: keywords may have no recent posts, or Threads served a login wall — try in Colab (where it's
tested) or widen `max_age_hours` / keywords.

---

## Step 2 — Verify storage (the bronze layer)

**What it does:** confirms the raw layer is well-formed and deduplicated (the hand-off the agent reads).

```bash
.venv/bin/python - <<'PY'
import json, glob
f = sorted(glob.glob("data/raw/threads_*.jsonl"))[-1]
rows = [json.loads(l) for l in open(f, encoding="utf-8")]
ids = [r["post_hash_id"] for r in rows]
print("file:", f)
print("rows:", len(rows), "| unique ids:", len(set(ids)), "(should be equal — dedup)")
print("with images:", sum(1 for r in rows if r["images_base64"]))
print("keywords:", {r["matched_keyword"] for r in rows})
PY
```

**Pass criteria:** rows == unique ids (no dupes); `posted_at` looks like a timestamp; some rows have images
(needed to exercise Step 6).

---

## Step 3 — Connector reads bronze → normalized items (`data/test/1_fetched.json`)

**What it does:** `connectors/threads.fetch()` loads the latest bronze file and maps each `SocialPost`
into the pipeline's normalized shape `{id, source, text, images, timestamp, author, matched_keyword}`.

```bash
.venv/bin/python - <<'PY'
import json, os
from connectors.threads import fetch
items = fetch()
os.makedirs("data/test", exist_ok=True)
json.dump(items, open("data/test/1_fetched.json","w",encoding="utf-8"), ensure_ascii=False)
print("fetched:", len(items))
s = items[0]
print(json.dumps({**s, "images": [f'<{len(s["images"])} img>']}, ensure_ascii=False, indent=2)[:700])
PY
```

**Pass criteria:** count matches bronze rows; every item has `source="threads"`, non-empty `text` (mostly),
`images` is a list of `data:...;base64,...` strings, `timestamp` is filled (falls back to `crawled_at` if
the post time was "Unknown").

---

## Step 4 — Preprocess (clean + filter + dedup) (`data/test/2_clean.json`)

**What it does:** `clean_text` strips URLs/emoji/@mentions/#tags, `is_meaningful` drops <4-word posts,
`deduplicate` removes near-identical text.

```bash
.venv/bin/python - <<'PY'
import json
from processors.preprocessor import preprocess
items = json.load(open("data/test/1_fetched.json", encoding="utf-8"))
out = preprocess(items)
json.dump(out, open("data/test/2_clean.json","w",encoding="utf-8"), ensure_ascii=False)
print(f"{len(items)} → {len(out)} after preprocess")
for it in out[:5]:
    print(" •", it["text"][:90])
PY
```

**Pass criteria:** count drops or stays equal; remaining texts are clean (no URLs/emoji); short/empty posts
removed. Eyeball that no clearly-real complaint was wrongly dropped.

---

## Step 5 — Sentiment filter (PhoBERT, keep negatives) (`data/test/3_negative.json`)

**What it does:** PhoBERT classifies each post; keeps NEG (LLM tiebreaker only for borderline scores).
First run downloads PhoBERT (~500MB).

```bash
.venv/bin/python - <<'PY'
import json
from processors.sentiment import is_negative
items = json.load(open("data/test/2_clean.json", encoding="utf-8"))
kept, dropped = [], []
for it in items:
    (kept if is_negative(it["text"]) else dropped).append(it)
json.dump(kept, open("data/test/3_negative.json","w",encoding="utf-8"), ensure_ascii=False)
print(f"{len(items)} → {len(kept)} negative kept, {len(dropped)} dropped")
print("\nKEPT:");    [print("  -", it["text"][:80]) for it in kept[:8]]
print("\nDROPPED:"); [print("  -", it["text"][:80]) for it in dropped[:8]]
PY
```

**Pass criteria:** complaints kept, praise/neutral dropped. Manually check a few — this is where
borderline Vietnamese sarcasm can slip; note any misses (tune `SENTIMENT_THRESHOLD` later).

---

## Step 6 — Image analysis (Gemma vision) (`data/test/4_imaged.json`)

**What it does:** for posts with images, Gemma describes the screenshot (base64 → vision). Attaches
`image_analysis` to the item. Posts without images pass through unchanged.

```bash
.venv/bin/python - <<'PY'
import json
from processors.image_analyzer import load_sample_images, analyze_image
items = json.load(open("data/test/3_negative.json", encoding="utf-8"))
samples = load_sample_images()   # [] is fine (no reference set yet)
n = 0
for it in items:
    if it.get("images"):
        try:
            it["image_analysis"] = analyze_image(it["images"][0], samples)
            n += 1
            print(f"  {it['id']}: {it['image_analysis'].get('description','')[:80]}")
        except Exception as e:
            print(f"  {it['id']}: image analysis FAILED — {e}")
json.dump(items, open("data/test/4_imaged.json","w",encoding="utf-8"), ensure_ascii=False)
print(f"analyzed {n} image post(s)")
PY
```

**Pass criteria:** posts with images get a sensible `image_analysis.description`. Images are base64 (from
the crawler), so they go to Gemma directly — no host-fetch issues. If you see 500/403 errors, the image is
a URL not base64 (shouldn't happen for Threads bronze).

---

## Step 7 — Issue extraction (LLM) (`data/test/5_extracted.json`)

**What it does:** Gemma turns each messy post (+ image description) into one clean English issue sentence.

```bash
.venv/bin/python - <<'PY'
import json
from processors.issue_extractor import extract_issue
items = json.load(open("data/test/4_imaged.json", encoding="utf-8"))
for it in items:
    desc = (it.get("image_analysis") or {}).get("description", "")
    it["extracted_issue"] = extract_issue(it["text"], image_description=desc)
    print(f"  {it['id']}: {it['extracted_issue']}")
json.dump(items, open("data/test/5_extracted.json","w",encoding="utf-8"), ensure_ascii=False)
print("extracted", len(items))
PY
```

**Pass criteria:** each `extracted_issue` is a single clear English sentence naming the failure/feature/error
— no emotion, no Vietnamese. This text drives RAG + grouping, so quality here matters most.

---

## Step 8 — Classification (RAG-grounded domain + segment) (`data/test/6_classified.json`)

**What it does:** retrieves similar taxonomy/known-issue examples, then Gemma assigns `domain` then `segment`
(validated against `config.DOMAINS`/`SEGMENTS`).

```bash
.venv/bin/python - <<'PY'
import json
from processors.classifier import classify_domain, classify_segment
items = json.load(open("data/test/5_extracted.json", encoding="utf-8"))
for it in items:
    it["domain"]  = classify_domain(it["extracted_issue"])
    it["segment"] = classify_segment(it["extracted_issue"], it["domain"])
    print(f"  {it['domain']:16} / {it['segment']:12} ← {it['extracted_issue'][:60]}")
json.dump(items, open("data/test/6_classified.json","w",encoding="utf-8"), ensure_ascii=False)
PY
```

**Pass criteria:** domains/segments look right. **Watch for "Other/General" on issues that clearly fit a
domain** (known accuracy gap — noted for a later fix). Flag any misses.

---

## Step 9 — Grouping (merge duplicates, count mentions) (`data/test/7_grouped.json`)

**What it does:** embeds all `extracted_issue`s, merges those with cosine ≥ `GROUPING_THRESHOLD` (0.82),
producing one row per issue with `mentions` + `sources`.

```bash
.venv/bin/python - <<'PY'
import json
from processors.grouper import group_similar
items = json.load(open("data/test/6_classified.json", encoding="utf-8"))
groups = group_similar(items)
json.dump(groups, open("data/test/7_grouped.json","w",encoding="utf-8"), ensure_ascii=False)
print(f"{len(items)} items → {len(groups)} groups")
for g in groups:
    print(f"  [{g['mentions']}x] {g['domain']}/{g['segment']}: {g['extracted_issue'][:60]}  sources={g['sources']}")
PY
```

**Pass criteria:** clearly-duplicate complaints merge into one group with `mentions>1`. **Watch for
paraphrased duplicates that stay separate** (known gap — threshold may be too strict; noted for a later
fix).

---

## Step 10 — Knowledge base lookup (RAG solutions)

**What it does:** for each grouped issue, retrieve the team's suggested approach from the KB.

```bash
.venv/bin/python - <<'PY'
import json
from knowledge_base.search import get_suggested_approach
groups = json.load(open("data/test/7_grouped.json", encoding="utf-8"))
for g in groups:
    print(f"\n# {g['extracted_issue'][:60]}")
    print(" ", get_suggested_approach(g["extracted_issue"])[:200].replace("\n"," "))
PY
```

**Pass criteria:** relevant issues return a real KB approach; unknown ones return the escalation fallback
("No known solution found…"). (The report step calls this internally — this is just to inspect it.)

---

## Step 11 — Report + guardrails (`output/<ts>_social_media.md`)

**What it does:** generates the markdown report (KB approaches + LLM exec summary), validates it.

```bash
.venv/bin/python - <<'PY'
import json
from report.generator import generate_report, save_report
from report.guardrails import check_report
groups = json.load(open("data/test/7_grouped.json", encoding="utf-8"))
report = generate_report(groups, job_name="Social Media")
gr = check_report(report, groups)
print("guardrails ok:", gr["ok"], "| issues:", gr["issues"])
path = save_report(report, "Social Media")
print("saved:", path)
print("\n----- REPORT -----\n", report[:1200])
PY
```

**Pass criteria:** `guardrails ok: True`; the report has a header, exec summary, and one table row per
group with the right domain/segment/mentions/sources/approach. Open the saved `.md` to read it.

---

## Step 12 — Index issues + agentic Q&A

**What it does:** stores the grouped issues in the `issues` vector collection, then answers a PO question
over them.

```bash
.venv/bin/python - <<'PY'
import json
from knowledge_base.issues_store import index_issues, answer_question
groups = json.load(open("data/test/7_grouped.json", encoding="utf-8"))
print("indexed:", index_issues(groups, job_name="Social Media"))
for q in ["What payment issues are users reporting?", "Any QR code problems this week?"]:
    print(f"\nQ: {q}\nA: {answer_question(q)}")
PY
```

**Pass criteria:** answers are grounded in the indexed issues (cite mentions/sources/dates) and say "nothing
relevant" when appropriate.

---

## Run the whole thing at once (for comparison)

After verifying steps individually, confirm the real end-to-end via the entrypoint (reads the latest
bronze, runs all stages):

```bash
.venv/bin/python -c "import json; from main import handle_payload; print(json.dumps(handle_payload({'action':'run','job':'social','dry_run':False}), indent=2, default=str))"
.venv/bin/python -c "from main import handle_payload; print(handle_payload({'action':'query','question':'summarize the top issues'})['answer'])"
```

`dry_run=False` makes the social job call `connectors.threads.fetch()` (your bronze). `dry_run=True` would
use mock data instead.

---

## Known issues (carry forward — fixes noted for later)

| Area | Issue | Effect on testing |
|------|-------|-------------------|
| Jira connector | Uses removed `/rest/api/2/search` (HTTP 410) | Real Jira crawl fails; migrate to `/rest/api/3/search/jql`. Test Threads instead for now. |
| Facebook | Needs real `FB_PAGE_IDS` + `FB_ACCESS_TOKEN`; crawls own Pages only | Skip unless you have Page tokens. |
| Classification | Some clear issues → `Other/General` | Note misclassifications in Step 8. |
| Grouping | Paraphrased duplicates not merged (threshold 0.82) | Note unmerged dupes in Step 9. |
| Image URLs | MaaS fetches image URLs server-side; some hosts 403 | N/A for Threads (base64), only affects URL-based sources. |

## Cleanup

```bash
rm -rf data/test/                 # intermediate artifacts
# bronze (data/raw/) and reports (output/) are kept; both are gitignored
```
