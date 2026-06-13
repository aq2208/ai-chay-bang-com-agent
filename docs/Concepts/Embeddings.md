# Embeddings

#concept #nlp #core

---

## Tier 1: Foundation

### TL;DR

Converts text into a list of numbers that captures its **meaning**, so you can find documents by meaning instead of keywords.

```
"cannot add money with card"  → [0.24, -0.40, 0.87, ...]
"top-up failure with Visa"    → [0.23, -0.41, 0.88, ...]  ← almost identical → found ✅

"weather is nice today"       → [-0.71, 0.33, -0.22, ...]  ← very different → not found
```

That's it. The rest (RAG, semantic search, clustering) are just applications of that one idea.

---

### Why Embeddings Are Needed

LLMs can't search. If you have 500 solution documents, you can't stuff them all into a prompt — context windows have limits, and even if they didn't, it'd cost a fortune. You need a way to find the right 2–3 documents *before* calling the LLM.

Keyword search fails here:

```
Query:    "cannot add money with card"
Document: "top-up failure with Visa"   ← same problem, zero keyword overlap → missed
```

Embeddings solve this by converting meaning into numbers that can be compared mathematically:

```
"cannot add money with card"  → [0.24, -0.40, 0.87, ...]
"top-up failure with Visa"    → [0.23, -0.41, 0.88, ...]
                                  ↑ almost identical → cosine similarity: 0.97 → found ✅
```

Same meaning → similar numbers → findable with a dot product.

### Why Plain Text Can't Do This

Plain text can do **one thing**: exact match.

```python
"E5001" in document  →  True/False
```

That's it. Everything else requires meaning, and plain text has no concept of meaning.

**Problem 1: Synonyms**

```
Query:    "can't add money"
Document: "top-up failure"
```

Zero words in common. Keyword search returns nothing. But they mean the same thing.

**Problem 2: Scale**

To find all payment-related complaints with plain text, you'd need a hand-written list of every possible phrasing:

```python
if "lỗi" in text or "error" in text or "fail" in text or
   "không nạp" in text or "nạp tiền" in text or ...:
```

This list is never complete. Someone writes `"tài khoản bị trừ tiền mà không vào"` — your list misses it. Embeddings handle any phrasing automatically.

**Problem 3: No "how similar" — only binary yes/no**

Plain text comparison is binary. Either the string matches or it doesn't. You can't ask "how close is this complaint to the E5001 pattern?" and get a score.

With vectors you get a score:

```
distance("top-up failure", "can't add money")     → 0.12  ← very close
distance("top-up failure", "app is slow")         → 0.87  ← very far
distance("top-up failure", "payment not working") → 0.18  ← close
```

That score is what makes clustering, ranking, and similarity thresholds possible.

**Problem 4: Language barrier**

```
Query (Vietnamese): "không nạp tiền được"
Document (English): "top-up failure"
```

No shared characters at all. Keyword search: zero results. A multilingual embedding model maps both to nearby vectors → found.

**The core reason:** plain text is a sequence of characters with no internal representation of what those characters *mean*. Two sentences can mean identically the same thing and share zero characters. Embeddings encode meaning as position in space — similar meanings end up close together, regardless of language, phrasing, or word choice.

### What Embeddings Enable (The Big Picture)

Embeddings are the bridge between **unstructured language** and **structured computation**. Once text is a vector, you can do math on meaning:

- Measure similarity between two texts
- Find the nearest neighbors to a query
- Cluster a thousand posts into groups
- Compare across languages

Without embeddings, text is just characters — you can only match it literally. With embeddings, you can operate on *meaning*. Here's what that unlocks in practice:

**Semantic Search / RAG**
User types "can't add money with card" → finds doc about "Visa top-up failure E5001" even though no words match. This is your Stage 7.

**Deduplication / Clustering**
Group 500 complaints into 20 distinct issue types without reading them manually — embed all 500 and cluster by vector proximity. Your Stage 8.

**Recommendation Systems**
"Users who liked X also like Y" — embed product/content descriptions, find nearby vectors. Netflix, Spotify, and Amazon all use this at scale.

**Long-Term Memory for Agents**
Store every past conversation turn as a vector. On a new turn, retrieve only the relevant ones. Without embeddings, an agent either has no memory or loads the entire history into context — expensive and hits limits fast.

**Cross-Language Search**
A multilingual model maps "không nạp tiền được" and "top-up failure" to nearby vectors. A Vietnamese user query finds an English KB doc. This is exactly why your pipeline uses `paraphrase-multilingual-MiniLM-L12-v2`.

**Anomaly / Novelty Detection**
If a complaint vector is far from every known cluster → it's a new type of issue your team has never seen. Flag it for human review instead of silently misclassifying it.

Anything you want to do with "meaning" at scale — search, group, compare, remember — requires converting text to vectors first.

### What an Embedding Is

An embedding converts text into a list of numbers (a vector) that captures its **meaning**.

```
"Top-up failed with Visa"      → [0.23, -0.41, 0.88, 0.12, ...]   (384 numbers)
"Cannot add money with card"   → [0.24, -0.40, 0.87, 0.13, ...]   ← very close!
"Weather is nice today"        → [-0.71, 0.33, -0.22, 0.91, ...]  ← very different
```

Two texts with similar meaning → similar vectors (small angle between them).
Two unrelated texts → very different vectors (large angle).

This is what makes **semantic search** possible: find documents by *meaning*, not just keywords.

### The Critical Mental Model: Vectors Find Text, They Don't Replace It

This is the most common misconception. LLMs only read **text**. Vectors are used to *find* the right text, not to replace it.

```
❌ Wrong mental model:
text → vector → feed vector into LLM

✅ Correct mental model:
text → vector → find similar vectors → retrieve original text → feed TEXT into LLM
```

The vector is like a library index card. You use the index to find the book, then you read the book — not the index card.

### Index Time vs Query Time — What Is a "Query"?

Every embedding workflow has two phases:

```
INDEX TIME (do once, at setup):
  documents = ["E5001 gateway timeout fix", "QR scan failure", ...]
  → embed each → store in vector DB

QUERY TIME (do at runtime, per search):
  query = "Visa card payment keeps failing"   ← this is the query
  → embed it → find closest document vectors → return matching docs
```

The **query** is the text you search *with*. The **documents** are what you search *through*. You embed both using the same model so they land in the same vector space — then distance tells you how relevant each document is to the query.

The query doesn't have to be a question. It's any text you use as the search input — a sentence, a phrase, a complaint summary. As long as it goes through the same embedding model as the indexed documents, the similarity math works.

In your pipeline:
- **Stage 7 (RAG)** — query is the extracted issue (`"Visa card top-up failing with error E5001"`), documents are KB solution files
- **Stage 8 (grouping)** — no query; all extracted issues are embedded and compared *against each other* to find clusters

### Minimal Working Example

```python
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

docs = [
    "E5001 means payment gateway timeout. Fix: increase retry to 3.",
    "QR code scan fails when merchant terminal firmware is outdated.",
    "OTP not received: check if phone number is correct in profile.",
]
doc_vectors = model.encode(docs)

query = "Visa card payment keeps failing"
query_vector = model.encode(query)

scores = util.cos_sim(query_vector, doc_vectors)
best_idx = scores.argmax()
print(docs[best_idx])
# → "E5001 means payment gateway timeout. Fix: increase retry to 3."
```

### Which Model to Use

| Model | Dims | Languages | Size | Use when |
|-------|------|-----------|------|---------|
| `all-MiniLM-L6-v2` | 384 | English | 80MB | English-only project |
| `paraphrase-multilingual-MiniLM-L12-v2` | 384 | 50+ langs incl. Vietnamese | 120MB | **Your project** ✅ |
| `text-embedding-3-small` | 1536 | All | API call | Highest quality, costs money |

```bash
pip install sentence-transformers
```

---

## Tier 2: How It Works

### Three Roles in a General Agent Pipeline

Embeddings appear in three distinct roles across agent systems. The underlying pattern is always the same — use vectors to find text, then let the LLM read the text — but the purpose differs.

**Role 1: Knowledge Retrieval (RAG)**
The agent has a large private knowledge base it can't fit in its prompt. Embeddings let it find the relevant piece on demand.

```
User asks a question
        ↓
Agent embeds the question → query vector
        ↓
Search vector DB → find closest document vectors
        ↓
Retrieve document TEXT → inject into prompt → LLM answers
```

**Role 2: Semantic Memory**
Agents that run over long sessions can't keep every past message in context — it gets expensive and hits limits. Embeddings make selective recall possible.

```
Every agent turn → embed the message → store in vector DB
        ↓
On new turn → embed current query → retrieve most relevant past turns
        ↓
Inject only the relevant memory into the prompt
```

The agent can recall things from 100 turns ago without needing all 100 turns in context.

**Role 3: Routing and Classification**
In multi-agent systems, embeddings help decide which agent or tool should handle a request by comparing the query against pre-embedded tool descriptions.

```
User: "my Visa top-up failed with E5001"
        ↓
Embed the query → compare against embedded tool descriptions:
  "search_knowledge_base: finds known solutions"  → similarity: 0.91 ✅
  "search_web: searches the internet"             → similarity: 0.34
  "create_jira_ticket: logs a new bug"            → similarity: 0.61
        ↓
Route to search_knowledge_base
```

**The universal pattern across all three roles:**

```
Setup:    TEXT → embed → store vector + original text in vector DB
Runtime:  QUERY → embed → find similar vectors → retrieve original TEXT
Use:      pass TEXT to LLM (never the vector)
```

Embeddings are always a bridge — they let you find the right text using math, then the LLM does what it's good at: reading and reasoning over that text.

In your Zalopay project, you use **Role 1** (RAG for KB lookups at Stage 7) and a variant of **Role 3** (semantic grouping to cluster similar complaints at Stage 8).

---

### Semantic Space

Embedding models map text into a high-dimensional "semantic space" where meaning is encoded as direction. Texts about similar topics point in similar directions. You can think of it like:

```
High-dimensional space (384 dimensions):

  [payment errors cluster]   ←→   [login problems cluster]   ←→   [weather cluster]
         ↑                                                                ↑
  "Visa payment fails"                                          "Nice day today"
  "Thẻ Visa không nạp được"   ← these two are close (multilingual model)
```

**What the dimensions are NOT:** individual dimensions have no human-interpretable meaning. You can't point to dimension 47 and say "this is the sentiment axis" or "this measures noun-ness." The meaning lives entirely in the *relationships between vectors* — which directions are close to which other directions. This is learned from billions of training examples, not designed by hand.

### Why Cosine Similarity, Not Euclidean Distance

Two ways to compare vectors:

**Euclidean distance** measures the straight-line distance between two points. Problem: a short text and a long text about the same topic produce vectors at different magnitudes (distances from origin), so they look far apart even if their *direction* is identical.

**Cosine similarity** measures the angle between two vectors. Direction = meaning. Magnitude is irrelevant — it doesn't matter how long or short the text was.

```python
from numpy import dot
from numpy.linalg import norm

def cosine_similarity(a, b):
    return dot(a, b) / (norm(a) * norm(b))
    # Returns -1 to 1: 1 = identical direction, 0 = orthogonal, -1 = opposite
```

| Score | Meaning |
|-------|---------|
| 1.0 | Identical meaning |
| 0.8+ | Very similar |
| 0.5–0.8 | Somewhat related |
| < 0.5 | Likely unrelated |

Always use cosine similarity (or dot product on normalized vectors) for semantic search. Never use Euclidean distance for comparing embeddings.

### Max Sequence Length — The Silent Truncation Trap

**This is the most important gotcha in production.**

Every embedding model has a maximum input length. If your text is longer, the model silently truncates it — no warning, no error, just a degraded embedding of the partial text.

| Model | Max tokens |
|-------|-----------|
| `paraphrase-multilingual-MiniLM-L12-v2` | **128 tokens** |
| `all-MiniLM-L6-v2` | 256 tokens |
| `all-mpnet-base-v2` | 384 tokens |

128 tokens is roughly 80–100 words. A long Jira ticket description or a verbose social media post will exceed this.

Check your text length before embedding:

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained(
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
tokens = tokenizer.encode("your text here")
print(f"Token count: {len(tokens)}")   # warn if > 128
```

**Fix: chunk long texts before embedding.** See Tier 3.

### Normalized Vectors

Most sentence transformer models output **normalized** vectors (magnitude = 1.0). When both vectors are normalized:

```
cosine_similarity(a, b) == dot(a, b)
```

This matters for performance — dot product skips the division step and is faster. ChromaDB and most vector databases use this internally. You can request normalized output explicitly:

```python
vectors = model.encode(texts, normalize_embeddings=True)
```

---

## Tier 3: Production Patterns

### Batch Encoding (5–10× Faster)

Never encode texts one at a time in a loop. The model is optimized for batch operations:

```python
# ❌ Slow — encodes one at a time
vectors = [model.encode(text) for text in texts]

# ✅ Fast — single batched call
vectors = model.encode(texts)

# With progress bar for large batches
vectors = model.encode(texts, show_progress_bar=True)
```

The speedup comes from the underlying matrix operations being heavily parallelized in batch form. For 100+ texts, this is a significant difference.

### Saving and Loading Embeddings

Embeddings are deterministic — same text always produces the same vector. Don't recompute on every run:

```python
import numpy as np

# Save after computing
vectors = model.encode(docs)
np.save("embeddings.npy", vectors)

# Load on subsequent runs
vectors = np.load("embeddings.npy")
```

For production with a vector DB, use ChromaDB's persistent client — it handles storage automatically:

```python
import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection("knowledge_base")
# Vectors survive process restarts
```

### Handling Long Texts (Chunking)

For texts that exceed the model's max sequence length, chunk before embedding:

```python
def chunk_text(text: str, max_words: int = 80) -> list[str]:
    words = text.split()
    return [
        " ".join(words[i:i + max_words])
        for i in range(0, len(words), max_words)
    ]
```

Two strategies depending on use case:

**For RAG:** Store each chunk as a separate document in the vector DB. At query time you retrieve the specific chunk that answers the question, not an average.

```python
for i, chunk in enumerate(chunk_text(long_doc)):
    collection.add(
        documents=[chunk],
        embeddings=model.encode([chunk]).tolist(),
        ids=[f"doc_{doc_id}_chunk_{i}"]
    )
```

**For deduplication/clustering:** Average chunk vectors to get one vector per document.

```python
def embed_long_text(text: str) -> np.ndarray:
    chunks = chunk_text(text)
    chunk_vectors = model.encode(chunks, normalize_embeddings=True)
    avg = chunk_vectors.mean(axis=0)
    return avg / np.linalg.norm(avg)   # re-normalize after averaging
```

### Semantic Deduplication / Clustering

Group similar complaints together to count "mentions" even when phrased differently:

```python
from sentence_transformers import util

def cluster_by_similarity(items: list[dict], threshold: float = 0.85) -> list[list[dict]]:
    texts = [i["text"] for i in items]
    vectors = model.encode(texts, normalize_embeddings=True)
    clusters = []
    used = set()

    for i, vec_i in enumerate(vectors):
        if i in used:
            continue
        cluster = [items[i]]
        used.add(i)
        for j in range(i + 1, len(vectors)):
            if j in used:
                continue
            score = float(util.cos_sim(vec_i, vectors[j]))
            if score >= threshold:
                cluster.append(items[j])
                used.add(j)
        clusters.append(cluster)

    return clusters

# "Visa top-up not working"      ┐
# "Cannot top up with Visa card" ├─ same cluster → report: "3 mentions"
# "Thẻ Visa không nạp được"     ┘
```

---

## Where Embeddings Fit in the Pipeline

### Use 1: RAG — Index Knowledge Base

```
Team writes solution docs
        ↓
chunk each doc (≤80 words per chunk)
        ↓
embed each chunk → vector
        ↓
store (text + vector) in ChromaDB
        ↓
[at query time]
        ↓
embed the issue → query vector
        ↓
find closest chunk vectors → retrieve text
        ↓
pass text to LLM as context
```

### Use 2: Semantic Deduplication

```
100 social posts about Visa top-up failures
        ↓
embed all posts → 100 vectors
        ↓
cluster by cosine similarity ≥ 0.85
        ↓
→ 12 distinct issue clusters
→ largest cluster: 23 posts
→ report: "23 mentions of Visa top-up failure"
```

---

## In Your Pipeline (Zalopay Project)

### The Most Important Design Decision: Embed the Extracted Issue, Not the Raw Text

This is explicitly flagged in [[Projects/Pipeline Deep Dive]] as a common mistake. Embedding runs at **Stage 7**, not Stage 1 — after the LLM has already extracted a clean issue statement.

```
Stage 1 — PREPROCESS  → clean raw text
Stage 5 — ISSUE EXTRACTION → "Visa card top-up failing with error E5001"
                                        ↓
Stage 7 — RAG     → EMBED extracted issue → search ChromaDB
Stage 8 — GROUPING → EMBED all extracted issues → cluster similar ones
```

Why this matters:

```python
# ❌ Embedding the raw messy text
embed("Zalopay bị lỗi rồi! 😡 Không nạp tiền được bằng Visa suốt 2 tiếng!!")
# → noisy vector: mixes language, emotion, product name, feature in one signal

# ✅ Embedding the clean extracted issue
embed("Visa card top-up failing with error E5001")
# → precise vector: represents exactly the technical problem
```

Two posts in completely different languages/styles that describe the same technical issue will both extract to nearly identical issue statements — and therefore cluster together correctly in Stage 8.

### Two Uses in This Project

**Use 1 — RAG (Stage 7): find the right KB doc**

```python
# Called once per item, after issue extraction
issue = "Visa card top-up failing with error E5001"
query_vector = embedder.encode(issue).tolist()

results = kb_collection.query(query_embeddings=[query_vector], n_results=2)
# ChromaDB returns "distances" (L2) — lower = more similar
relevant = [doc for doc, dist in zip(results["documents"][0], results["distances"][0])
            if dist < 0.5]
```

Note on ChromaDB distances: ChromaDB's default metric is **L2 (Euclidean) distance**, not cosine similarity. Lower distance = more similar. The threshold `< 0.5` means "close enough to be relevant". This is different from cosine similarity where higher = more similar. If you create the collection with `metadata={"hnsw:space": "cosine"}`, you can switch to cosine distance.

**Use 2 — Semantic Grouping (Stage 8): count mentions accurately**

```python
# Called once per batch, after all items are enriched
grouped = group_by_similarity(enriched_items, threshold=0.82)
# 7 posts all about Visa E5001 → 1 group with mentions=7
```

The threshold `0.82` is the project's calibrated value. Below 0.82, different-but-related issues incorrectly merge. Above 0.82, paraphrases of the same issue split into separate rows.

### Where the Embedding Code Lives

Per the revised file structure in [[Projects/Architecture Review]]:

| File | What it does |
|------|-------------|
| `knowledge_base/search.py` | `search_knowledge_base()` — RAG lookup at Stage 7 |
| `processors/grouper.py` | `group_by_similarity()` — semantic grouping at Stage 8 |

Both use the same `embedder` instance (`paraphrase-multilingual-MiniLM-L12-v2`). Load it once at module import, not per-call.

### KB Doc Chunking

Solution docs in `knowledge_base/docs/` should be written concisely — ideally under 80 words per doc (within the model's 128-token limit). If a doc is longer, index it as separate chunks (one per issue type, one per resolution step). Avoid indexing the whole file as one vector or the tail gets silently cut.

```python
# When indexing KB docs
for filename in os.listdir(docs_folder):
    with open(f"{docs_folder}/{filename}") as f:
        text = f.read()
    # Chunk if long
    chunks = chunk_text(text, max_words=80) if len(text.split()) > 80 else [text]
    for i, chunk in enumerate(chunks):
        kb_collection.add(
            documents=[chunk],
            embeddings=[embedder.encode(chunk).tolist()],
            ids=[f"{filename}_chunk_{i}"]
        )
```

---

## Related Notes

- [[Concepts/How the NLP Concepts Connect]] — how all four NLP concepts fit together in the pipeline
- [[Concepts/RAG - Retrieval-Augmented Generation]] — how embeddings power RAG
- [[Tools/Vector Databases]] — where vectors are stored
- [[Concepts/Tokenization & Text Preprocessing]] — clean text before embedding
- [[Concepts/LLM as a Processing Step]] — embeddings help LLM, but don't replace text input
- [[Projects/Pipeline Deep Dive]] — full stage-by-stage walkthrough showing exactly where embeddings fit
