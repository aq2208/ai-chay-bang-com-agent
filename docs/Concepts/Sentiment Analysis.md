# Sentiment Analysis

#concept #nlp

> [!note] In the project: **PhoBERT** (`wonrax/phobert-base-vietnamese-sentiment`) does the first pass;
> the LLM tiebreaker for borderline cases is **`google/gemma-4-31b-it` via AgentBase MaaS** (any
> Claude/Gemini references below are illustrative). Canonical design: [[Projects/00 - Project Home]].

---

## Tier 1: Foundation

### What It Is

Sentiment analysis classifies text by **emotional tone** — most commonly into **positive**, **negative**, or **neutral**. Some models also output fine-grained emotions (anger, joy, fear) or intensity scores.

The task sounds simple but is surprisingly hard:
- "ZaloPay is *interesting*" — positive or sarcastic?
- "Không lỗi nào cả" — genuinely no bugs (positive) or sarcastic praise (negative)?
- "Ứng dụng hơi lag nhưng ok" — mixed: mildly negative + acceptable

For this project: sentiment analysis is the **filter** — it keeps only negative posts (complaints, problems) and drops positive/neutral ones before any expensive LLM calls.

### ML Model vs LLM — Quick Decision

| | ML Model | LLM |
|--|----------|-----|
| Speed | ~10ms per post | ~500ms per post |
| Cost | Free, offline | ~$0.001 per 1,000 posts |
| Vietnamese accuracy | Medium | High |
| Nuance (sarcasm, mixed) | Low | High |
| Use when | High-confidence cases | Borderline or ambiguous |

**Best practice:** use ML first, LLM only on borderline cases. See the hybrid pattern in Tier 3.

### Minimal Working Example

```python
from transformers import pipeline

_sentiment_model = pipeline(
    "text-classification",
    model="wonrax/phobert-base-vietnamese-sentiment"
    # Labels: NEG, POS, NEU
)

result = _sentiment_model("Zalopay bị lỗi rồi, không nạp tiền được!")
# → [{"label": "NEG", "score": 0.94}]

result = _sentiment_model("App tuyệt vời, dùng rất mượt!")
# → [{"label": "POS", "score": 0.97}]
```

---

## Tier 2: How It Works

### Rule-Based vs Neural Models

**Rule-based (pre-2018):** Maintains a lexicon — a dictionary mapping words to sentiment scores (`"tệ"` → −1.0, `"tuyệt"` → +1.0). Sums or averages scores.

Problems:
- Doesn't handle negation: "không tệ" sums to negative but means neutral/positive
- Misses context: "giá cắt cổ" (lit. "throat-cutting price") is highly negative but no single word signals it

**Neural / Transformer-based (modern):** Pre-trained language models like PhoBERT read the **entire sentence at once** using attention mechanisms. Each word's representation is influenced by every other word — "không tệ" is processed as a unit, not word-by-word.

Training:
1. Pre-train on massive unlabeled text (predicts masked words — self-supervised)
2. Fine-tune on labeled sentiment data (text → positive/negative/neutral)

Result: the model learns negation, intensifiers, sarcasm markers without explicit rules. When you call `pipeline("text-classification")`, you're running inference on a ~125M parameter model.

### Confidence Scores

The model outputs a softmax probability distribution over labels. A score of `0.94` means the model assigns 94% probability to that label and splits the remaining 6% across others.

```python
result = _sentiment_model("Ứng dụng hơi chậm nhưng ok")[0]
# → {"label": "NEU", "score": 0.61}
# Score of 0.61 = borderline. For a 3-class problem, random chance is 0.33.
```

**Confidence zones:**

| Score | Interpretation |
|-------|---------------|
| ≥ 0.80 | High confidence — trust the label |
| 0.50–0.80 | Medium confidence — consider LLM verification |
| < 0.50 | Low confidence — model is nearly guessing |

### Precision vs Recall Trade-Off

For filtering complaints, **recall matters more than precision**:

- **High recall** = catch most real complaints, even at the cost of including some borderline neutral posts
- **High precision** = only include clear complaints, at the cost of missing borderline ones

Missing a complaint that reaches customers (low recall) is worse than including one ambiguous post in your analysis (low precision). Set your threshold accordingly — err on the side of keeping borderline posts.

### Vietnamese Sentiment Challenges

Vietnamese is harder than English for sentiment for four structural reasons:

**1. Tone marks change meaning completely**

Vietnamese is tonal — the same syllable with different diacritics means entirely different things:
- "ma" (ghost), "má" (cheek), "mà" (but), "mả" (tomb), "mã" (horse), "mạ" (rice seedling)

Users on mobile often **omit tone marks** (Telex without diacritics):
- "Zalopay bi loi" = "ZaloPay bị lỗi" (ZaloPay has an error) — but without marks, models may not recognize "loi" as "lỗi"

Use models trained on both normalized and non-normalized Vietnamese, or run tone restoration preprocessing.

**2. Sarcasm is structurally positive but semantically negative**

```
"ZaloPay hay thật đấy"
Literal: "ZaloPay is truly great"
Actual: dripping sarcasm said after an error
```

ML models struggle with this. An LLM with context understanding handles it better.

**3. Mixed language and code-switching**

Users naturally mix Vietnamese + English + emoji:
- "App bị crash hoài, so annoying 😤"
- "Lỗi 502 again?? 💀 bao giờ fix vậy"

Models trained on pure Vietnamese or pure English perform poorly on mixed text. Choose:
- **PhoBERT** — Vietnamese-only, best accuracy for pure Vietnamese
- **XLM-RoBERTa** — 100 languages including Vietnamese, better for mixed-language posts

**4. Informal spelling and abbreviation**

| Abbreviation | Meaning |
|-------------|---------|
| "ko" / "k" | "không" (not/no) |
| "dc" | "được" (okay/can) |
| "bik" | "biết" (know) |
| "j" | "gì" (what) |
| "ns" | "nói" (say) |

Models fine-tuned on social data (Twitter/Facebook) handle this better than models trained on formal text.

**Model comparison:**

| | PhoBERT | XLM-RoBERTa (twitter) |
|--|---------|----------------------|
| Pure Vietnamese accuracy | Higher | Medium-High |
| Mixed language | Poor | Good |
| Tone-mark-free text | Medium | Medium |
| Size | ~135M params | ~125M params |

---

## Tier 3: Production Patterns

### Load the Model Once

Loading a transformer takes 1–3 seconds and uses ~500MB RAM. **Never load inside a function called per-post:**

```python
# ❌ Wrong — reloads model for every post
def is_negative(text: str) -> bool:
    model = pipeline("text-classification", model="...")  # expensive every call
    return model(text)[0]["label"] == "NEG"

# ✅ Correct — load at module level, reuse
_sentiment_model = pipeline(
    "text-classification",
    model="wonrax/phobert-base-vietnamese-sentiment",
    device=0 if torch.cuda.is_available() else -1
)

def is_negative(text: str) -> bool:
    return _sentiment_model(text[:512])[0]["label"] == "NEG"
```

### Batch Processing

When processing many posts, batching is significantly faster than one-by-one:

```python
def filter_negative_batch(posts: list[dict], batch_size: int = 32) -> list[dict]:
    texts = [p["text"][:512] for p in posts]
    negative = []
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        batch_posts = posts[i:i + batch_size]
        results = _sentiment_model(batch_texts)
        for post, result in zip(batch_posts, results):
            if result["label"] == "NEG" and result["score"] >= 0.75:
                negative.append(post)
    return negative
```

On GPU: ~10ms per post → ~0.3ms per post with batching. Even on CPU, batching reduces overhead 3–5×.

### The Hybrid Approach: ML → LLM Tiebreaker

ML handles clear cases cheaply. LLM handles ambiguous cases accurately. In practice ~70–80% of posts are decided by ML, keeping LLM costs low:

```python
import anthropic
client = anthropic.Anthropic()

def _llm_sentiment_check(text: str) -> bool:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=5,
        system="Is this text expressing a complaint or problem? Reply YES or NO only.",
        messages=[{"role": "user", "content": text}]
    )
    return "YES" in response.content[0].text.upper()

def is_negative(text: str) -> tuple[bool, float]:
    result = _sentiment_model(text[:512])[0]
    label = result["label"]
    score = result["score"]

    if label == "NEG" and score >= 0.75:
        return True, score     # clearly negative
    if label == "POS" and score >= 0.75:
        return False, score    # clearly positive
    # Borderline (0.4–0.75 or NEU) → ask LLM as tiebreaker
    return _llm_sentiment_check(text), score
```

### Evaluating Quality

If you have even 100 manually labeled posts, measure classifier quality before deploying:

```python
from sklearn.metrics import classification_report

y_true = ["NEG", "POS", "NEG", "NEU", ...]  # hand-labeled
y_pred = [_sentiment_model(text[:512])[0]["label"] for text in texts]

print(classification_report(y_true, y_pred))
```

For complaint filtering, optimize for **recall on the NEG class** — catching all complaints matters more than avoiding false positives.

### Handling LLM Errors

The LLM tiebreaker can fail (rate limit, timeout, network error). Always have a fallback:

```python
def _llm_sentiment_check_safe(text: str) -> bool:
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            system="Is this text expressing a complaint or problem? Reply YES or NO only.",
            messages=[{"role": "user", "content": text}]
        )
        return "YES" in response.content[0].text.upper()
    except Exception:
        return True  # on error, keep the post — better to include than to miss a complaint
```

Failing open (keep the post on error) aligns with the recall-over-precision preference. The LLM report step downstream will still analyze it.

### Fine-Tuning on Domain Data

If off-the-shelf PhoBERT performs poorly on ZaloPay-specific Vietnamese, fine-tune on ~500+ labeled posts:

```python
from transformers import AutoModelForSequenceClassification, TrainingArguments, Trainer

model = AutoModelForSequenceClassification.from_pretrained(
    "vinai/phobert-base",
    num_labels=3  # NEG, POS, NEU
)

training_args = TrainingArguments(
    output_dir="./phobert-zalopay-sentiment",
    num_train_epochs=3,
    per_device_train_batch_size=16,
    evaluation_strategy="epoch",
)
```

500 labeled examples typically improves accuracy 5–15% on domain-specific text. Worth doing post-hackathon if the model struggles with ZaloPay-specific vocabulary.

---

## In Your Pipeline (ZaloPay Project)

### Stage 3: Social Media Filter

Sentiment analysis is **Stage 3**, social media job only. Jira tickets skip it entirely — all tickets are by definition complaints.

```
Stage 0 — FETCH posts from Facebook / Threads
    ↓
Stage 1 — PREPROCESS  (clean_text, deduplicate)
    ↓
Stage 2 — KEYWORD FILTER  (keep posts mentioning ZaloPay keywords)
    ↓
Stage 3 — SENTIMENT ANALYSIS  ← you are here
    keep only is_negative == True
    ↓
~40% of posts remain
    ↓
Stage 4 — IMAGE ANALYSIS (Claude Vision)
    ↓
Stage 5 — ISSUE EXTRACTION (Haiku)
```

**Why not on Jira?** Jira tickets are already complaints by definition — they don't need a sentiment filter. Only social media posts are a mixed bag of positive, neutral, and negative.

### The Confirmed Model and Thresholds

From [[Projects/Architecture Review]] (Gap 1 resolution) and [[Projects/Pipeline Deep Dive]]:

- **Model:** `wonrax/phobert-base-vietnamese-sentiment` (PhoBERT fine-tuned on Vietnamese social data)
- **Labels:** `NEG`, `POS`, `NEU`
- **High-confidence threshold:** `score >= 0.75` → trust ML label, skip LLM
- **Borderline range:** `score < 0.75` or label `NEU` → send to LLM tiebreaker

```python
# processors/sentiment.py

from transformers import pipeline
import anthropic

_sentiment_model = pipeline(
    "text-classification",
    model="wonrax/phobert-base-vietnamese-sentiment"
)
_client = anthropic.Anthropic()

def is_negative(text: str) -> tuple[bool, float]:
    result = _sentiment_model(text[:512])[0]
    label, score = result["label"], result["score"]

    if label == "NEG" and score >= 0.75:
        return True, score

    if label == "POS" and score >= 0.75:
        return False, score

    # Borderline → LLM tiebreaker
    llm_result = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=5,
        system="Is this text expressing a complaint or problem? Reply YES or NO only.",
        messages=[{"role": "user", "content": text}]
    )
    is_neg = "YES" in llm_result.content[0].text.upper()
    return is_neg, score
```

### Why Preprocessing Runs First (Stage 1 before Stage 3)

PhoBERT was not trained on text containing raw URLs, emoji, or `!!!!!!`. These tokens appear in its vocabulary as out-of-distribution noise, and their presence can shift confidence scores unpredictably.

Example: the post `"Zalopay bị lỗi rồi!!!! 😡😡 http://fb.com/photo/123"` may score lower confidence than the cleaned `"Zalopay bị lỗi rồi!"` even though they express the same sentiment. Running `clean_text()` first makes PhoBERT's scores more reliable and pushes more posts into the high-confidence zone (avoiding unnecessary LLM calls).

See [[Concepts/Tokenization & Text Preprocessing]] for the cleaning function used in Stage 1.

### Expected Filter Rate

After sentiment filtering, roughly **40% of posts remain** as negative. This varies by platform and brand health, but social media mentions skew heavily negative — users who are happy rarely post publicly.

This 40% is what all subsequent expensive steps (image analysis, LLM extraction, classification) run on. The 60% filtered out here costs nothing downstream.

### Where the Code Lives

```
processors/
└── sentiment.py    ← is_negative(), filter_negative_batch()
```

The model is loaded once when `sentiment.py` is imported. Both the Jira job and Social Media job import from here, but only the Social Media job (`jobs/social_job.py`) calls `is_negative()`.

---

## Production Checklist

- [ ] Load model once at startup, not per-request
- [ ] Cap input at 512 tokens (PhoBERT's context limit)
- [ ] Use batching when processing > 10 posts at a time
- [ ] Fail open on LLM errors — keep the post rather than silently dropping it
- [ ] Log confidence scores — monitor for distribution shifts over time
- [ ] Set a hard timeout on LLM tiebreaker calls (~5s) to prevent pipeline stalls
- [ ] Test on a sample of manually labeled posts before deploying

---

## Related Notes

- [[Concepts/How the NLP Concepts Connect]] — how all four NLP concepts fit together in the pipeline
- [[Concepts/Tokenization & Text Preprocessing]] — clean text before sentiment analysis; cleaning improves PhoBERT confidence scores
- [[Concepts/Embeddings]] — the other pre-LLM processing step; runs at Stage 7, not Stage 3
- [[Concepts/LLM as a Processing Step]] — when to use LLM vs ML model
- [[Projects/Architecture]] — full pipeline diagram
- [[Projects/Pipeline Deep Dive]] — complete stage-by-stage walkthrough with real input/output examples
- [[Projects/Architecture Review]] — Gap 1 resolution: PhoBERT + LLM tiebreaker pattern confirmed
