# Tokenization & Text Preprocessing

#concept #nlp

---

## Tier 1: Foundation

### Two Things Called "Tokenization"

"Tokenization" means two different things in NLP. Knowing which one you're dealing with saves a lot of confusion:

| | What it is | Who does it | Do you control it? |
|--|-----------|-------------|-------------------|
| **LLM tokenization** | Splits text into subword pieces the model reads internally | The model's built-in BPE tokenizer | No — automatic |
| **Text preprocessing** | Cleans and normalizes raw text before it enters the pipeline | You | Yes — this is what this doc covers |

When building a pipeline, you only deal with the second one. The model handles the first automatically.

### Why Preprocessing Matters

Raw social media text is noisy:
```
"Zalopay bị lỗi rồi!!!! 😡😡 Không nạp tiền được suốt 2 tiếng #zalopay http://fb.com/photo/123"
```

This causes two problems if you feed it unclean to an embedding model or LLM:

1. **Worse embeddings** — URLs, emoji, and hashtags are meaningless noise that shifts the vector away from the actual semantic content
2. **Higher LLM cost** — each URL is ~15–20 tokens; each emoji is 1–3 tokens; you pay for every one

After cleaning:
```
"zalopay lỗi không nạp tiền được"
```

Cleaner input → better embeddings → better search results → better LLM output → lower cost.

### The Core Cleaning Pipeline

```python
import re
import unicodedata

def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)           # Vietnamese Unicode safety
    text = re.sub(r'http\S+', '', text)                 # remove URLs
    text = re.sub(r'#\w+', '', text)                    # remove hashtags
    text = re.sub(r'@\w+', '', text)                    # remove @mentions
    text = re.sub(r'[^\w\sÀ-ɏḀ-ỿ]', ' ', text)  # remove emoji/symbols, keep Vietnamese
    text = re.sub(r'[!?]{2,}', '!', text)              # normalize !!! → ! (helps sentiment models)
    text = re.sub(r'\s+', ' ', text).strip()            # collapse whitespace
    return text.lower()
```

Always validate after cleaning — it can produce an empty string:

```python
text = clean_text(raw)
if not text:
    return None  # drop this item
```

### What You Don't Need to Do

| Task | Do you need it? | Why |
|------|----------------|-----|
| Manual tokenization | ❌ No | Embedding models tokenize internally |
| Stemming / lemmatization | ❌ No | LLMs understand word forms natively |
| Stop word removal | ❌ No | Modern models handle them fine |
| POS tagging | ❌ No | Overkill for this use case |
| URL removal | ✅ Yes | Noise for embeddings + wastes LLM tokens |
| Emoji removal | ✅ Yes | Breaks some models, meaningless noise |
| Unicode normalization | ✅ Yes | Vietnamese text safety |
| Deduplication | ✅ Yes | Avoids inflating mention counts |

---

## Tier 2: How It Works

### BPE Subword Tokenization (What the Model Does Internally)

When you pass text to an embedding model or LLM, the model first runs it through a **BPE (Byte Pair Encoding) tokenizer** — a learned vocabulary of subword pieces. This happens automatically; you never see it.

Example of what the model internally sees:
```
"unhappiness"       → ["un", "happiness"]
"ZaloPay"           → ["Zalo", "Pay"]
"xk92jf"            → ["x", "k", "9", "2", "j", "f"]   ← unknown, falls back to chars
"http://fb.com/123" → ["http", "://", "fb", ".", "com", "/", "1", "2", "3", ...]
```

Junk tokens — random URLs, userids, error codes — produce noisy subword splits. `"http://fb.com/photo/123abc"` might tokenize into 15–25 random pieces that pull the embedding vector toward noise and away from the actual meaning. This is why you clean first.

### How Cleaning Affects Token Count and Cost

LLMs charge per input token. Preprocessing directly reduces your bill:

| Content | Approximate tokens |
|---------|-------------------|
| One URL `http://fb.com/photo/123` | 15–20 tokens |
| One hashtag `#zalopay` | 3–5 tokens |
| Three emoji `😡😡😡` | 3–9 tokens |
| Typical post after cleaning | 20–40 fewer tokens |

At high volume (hundreds of posts/day), this compounds. More importantly, the LLM context window has a limit — removing junk leaves more room for actual content.

### Unicode Normalization for Vietnamese

Vietnamese characters exist in two Unicode forms that look identical but aren't:

```python
a = "lỗi"   # NFC:  ỗ is one composed character  (U+1ED7)
b = "lỗi"   # NFD:  ỗ is three characters         (o + combining circumflex + combining tilde)

a == b       # → False!
len(a)       # → 3
len(b)       # → 5
```

This matters for deduplication: two identical-looking posts may not match because one was submitted from iOS (NFC) and another from Android (NFD). Always normalize to NFC first:

```python
import unicodedata

text = unicodedata.normalize("NFC", text)
```

This is already included in the `clean_text` function above.

### Language Detection

Useful when handling Vietnamese and English differently:

```python
from langdetect import detect

lang = detect("Zalopay bị lỗi rồi")  # → "vi"
lang = detect("ZaloPay is broken")    # → "en"
```

`langdetect` can misfire on very short texts (< 20 characters). Always apply length filtering before language detection.

### Deduplication

Remove posts that say essentially the same thing:

```python
def deduplicate(items: list[dict]) -> list[dict]:
    seen_texts = set()
    unique = []
    for item in items:
        key = item["text"][:100].lower()
        if key not in seen_texts:
            seen_texts.add(key)
            unique.append(item)
    return unique
```

This catches exact or near-exact duplicates. For semantic duplicates (same complaint, different phrasing), use embeddings — see [[Concepts/Embeddings]].

### Length Filter

Drop posts too short to be meaningful:

```python
def is_meaningful(text: str, min_words: int = 5) -> bool:
    return len(text.split()) >= min_words

# "Lỗi"                                  → 1 word  → drop
# "Không nạp tiền được bằng Visa"        → 6 words → keep
```

---

## Tier 3: Production Patterns

### Batch Processing

Clean a list of posts in one pass, handling edge cases along the way:

```python
def preprocess_batch(items: list[dict]) -> list[dict]:
    results = []
    for item in items:
        raw = item.get("text") or ""
        if not isinstance(raw, str):
            continue
        cleaned = clean_text(raw)
        if not cleaned or not is_meaningful(cleaned):
            continue
        results.append({**item, "text": cleaned})
    return deduplicate(results)
```

### Edge Case Handling

Always guard against non-string and empty inputs. Post-cleaning, the text can be empty even if the original wasn't — a post that was just `"!!! 😡😡 http://fb.com/123 #zalopay"` becomes `""` after cleaning:

```python
def safe_clean(text) -> str | None:
    if not isinstance(text, str):
        return None
    cleaned = clean_text(text)
    return cleaned if cleaned else None
```

### Vietnamese Word Segmentation (When You Need It)

`underthesea` does proper Vietnamese word segmentation — compound words like `nạp tiền` stay together instead of being split:

```python
from underthesea import word_tokenize

tokens = word_tokenize("Zalopay không nạp tiền được")
# → ["Zalopay", "không", "nạp tiền", "được"]
# Note: "nạp tiền" is one token (compound word meaning "top up")
```

**When to use it:**
- Keyword matching where compound words matter
- Classical ML features (TF-IDF, bag-of-words)

**When NOT to use it:**
- Passing text to embedding models — they handle Vietnamese internally, just pass clean text

**Gotcha:** `underthesea` has a 2–3 second startup penalty on first import due to model loading. Import it once at module level, not inside a function called repeatedly.

---

## Where This Fits in the Pipeline

```
Raw post text
    ↓
normalize_unicode()   ← NFC normalization (Vietnamese safety)
    ↓
clean_text()          ← remove URLs, emoji, noise
    ↓
is_meaningful()       ← drop very short posts
    ↓
deduplicate()         ← drop exact near-duplicates
    ↓
→ ready for embedding and sentiment analysis
```

---

## In Your Pipeline (ZaloPay Project)

### Where Preprocessing Runs

Preprocessing is **Stage 1** in both pipeline jobs — the very first step after data is fetched. Nothing downstream (sentiment model, LLM, embeddings) sees raw text.

```
Stage 0 — FETCH raw posts from Jira / Facebook / Threads
    ↓
Stage 1 — PREPROCESS  ← you are here
    clean_text()
    is_meaningful()
    deduplicate()
    ↓
Stage 2 — KEYWORD FILTER  (social only)
    ↓
Stage 3 — SENTIMENT ANALYSIS (PhoBERT)
```

### Why Vietnamese Character Preservation Matters Here

The regex `[^\w\s]` — which you'll see in many examples online — **strips Vietnamese diacritics** on systems where Python's `\w` only matches ASCII word characters. A post containing `"không nạp tiền được"` becomes `"khng np tin c"` — unreadable noise.

The fix in this project uses an explicit Unicode range to protect Vietnamese characters:

```python
# ❌ Strips Vietnamese on some systems
re.sub(r'[^\w\s]', ' ', text)

# ✅ Explicitly keeps Vietnamese character ranges (U+00C0–U+024F and U+1E00–U+1EFF)
re.sub(r'[^\w\sÀ-ɏḀ-ỿ]', ' ', text)
```

### The `!!!` → `!` Normalization

PhoBERT (the sentiment model, Stage 3) was trained on somewhat normalized text. Multiple exclamation marks contribute noise without adding signal — `"lỗi!!!!!!"` and `"lỗi!"` express the same sentiment. Collapsing them improves classification confidence:

```python
text = re.sub(r'[!?]{2,}', '!', text)  # done in clean_text
```

### PhoBERT's 512-Token Limit (Stage 3)

The downstream sentiment model truncates inputs at 512 tokens. Since preprocessing runs first, a well-cleaned post will comfortably fit within this limit. A post containing a long URL that wasn't cleaned could eat 15–20 tokens unnecessarily, leaving less room for meaningful content. Preprocessing makes the 512-token limit a non-issue in practice.

### Keyword Matching Depends on Consistent Normalization

After Stage 1, the keyword filter (Stage 2) checks for terms like `"zalopay"`, `"nạp tiền"`, `"ví điện tử"`. This only works reliably if the text is:
- Lowercased (so `"ZaloPay"` matches `"zalopay"`)
- NFC normalized (so the Vietnamese compound `"nạp tiền"` is byte-for-byte identical to the keyword string)

Skipping normalization causes keyword misses that are invisible and hard to debug.

---

## Related Notes

- [[Concepts/How the NLP Concepts Connect]] — how all four NLP concepts fit together in the pipeline
- [[Concepts/Embeddings]] — what happens after cleaning
- [[Concepts/Sentiment Analysis]] — next preprocessing step
- [[Projects/Architecture]] — where preprocessing fits in the full pipeline
- [[Projects/Pipeline Deep Dive]] — full stage-by-stage walkthrough with real examples
