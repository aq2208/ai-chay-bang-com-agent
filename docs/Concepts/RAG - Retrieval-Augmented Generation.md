# RAG — Retrieval-Augmented Generation

#concept #advanced

---

## Tier 1: Foundation

### The Problem RAG Solves

LLMs have a knowledge cutoff and don't know about **your** specific documents. RAG lets you inject relevant private knowledge into the prompt on demand — at query time, not at training time.

**Without RAG:** "I don't know about the contents of your 500-page manual."
**With RAG:** Agent searches the manual, finds the relevant section, answers accurately.

This is the key distinction from fine-tuning:

| | RAG | Fine-tuning |
|--|-----|------------|
| Best for | Private / dynamic knowledge (your docs, your KB) | Changing model style, tone, or behavior |
| When knowledge changes | Re-index docs — no retraining | Retrain the model |
| Hallucination risk | Low — LLM reads the actual doc | Higher — model must memorize facts |
| Cost | Cheap (indexing + inference) | Expensive (GPU training time) |

For a knowledge base that changes (team adds solution docs, fixes are updated), RAG is the right choice.

### Two-Phase Model

```
Phase 1: Indexing (do once, or when KB changes)
──────────────────────────────────────────────
Documents → Split into chunks → Embed each chunk → Store in vector DB

Phase 2: Retrieval (do at query time, per question)
────────────────────────────────────────────────────
Query → Embed query → Find similar chunks → Retrieve TEXT → Inject into prompt → LLM answers
```

The vector DB never goes to the LLM. You use it to *find* the right text, then the LLM reads the text.

### Minimal Working Example

```python
import chromadb
from sentence_transformers import SentenceTransformer

embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
db = chromadb.Client()
collection = db.create_collection("knowledge_base")

# --- INDEX (do once) ---
documents = [
    "E5001 means payment gateway timeout. Fix: increase retry to 3.",
    "QR code scan fails when merchant terminal firmware is outdated.",
    "OTP not received: check if phone number is correct in profile.",
]
collection.add(
    documents=documents,
    embeddings=embedder.encode(documents).tolist(),
    ids=[f"doc_{i}" for i in range(len(documents))]
)

# --- RETRIEVE (do at query time) ---
def search_kb(query: str, n_results: int = 2) -> str:
    results = collection.query(
        query_embeddings=embedder.encode([query]).tolist(),
        n_results=n_results
    )
    return "\n---\n".join(results["documents"][0])

print(search_kb("Visa card payment keeps failing"))
# → "E5001 means payment gateway timeout. Fix: increase retry to 3."
```

---

## Tier 2: How It Works

### Why Chunking Matters

If you index a 5,000-word document as a single vector, the embedding averages across all the topics in that doc — diluting the signal. A query about "E5001 error" won't reliably surface a doc that also covers QR failures, login issues, and billing.

Chunk documents into focused pieces before indexing:

| Strategy | How | Best for |
|----------|-----|---------|
| Fixed size | Split every N tokens/words | General use |
| By paragraph | Split on `\n\n` | Articles, guides |
| By sentence | Split on `.` | Q&A, fact lookup |
| By section | Split on `##` headings | Structured docs |

```python
def chunk_document(text: str, max_words: int = 80) -> list[str]:
    paragraphs = text.split("\n\n")
    chunks, current = [], ""
    for para in paragraphs:
        if len((current + para).split()) <= max_words:
            current += para + "\n\n"
        else:
            if current:
                chunks.append(current.strip())
            current = para + "\n\n"
    if current:
        chunks.append(current.strip())
    return chunks
```

80 words keeps chunks within the 128-token limit of `paraphrase-multilingual-MiniLM-L12-v2`. Longer chunks get silently truncated at embedding time — see [[Concepts/Embeddings]] for details.

### Similarity Threshold — Don't Retrieve Junk

Vector search always returns *something* — even if nothing in the KB is relevant to the query. Without a threshold, RAG injects irrelevant documents and the LLM hallucinates a response based on them.

Always filter results by a similarity cutoff:

```python
results = collection.query(query_embeddings=[...], n_results=3)
documents = results["documents"][0]
distances = results["distances"][0]   # L2 distance: lower = more similar

# Only inject docs that are actually relevant
relevant = [doc for doc, dist in zip(documents, distances) if dist < 0.5]

if not relevant:
    return "No known solution found. Escalate to engineering team."
return "\n---\n".join(relevant)
```

If no docs pass the threshold, return a fallback rather than forcing the LLM to make something up.

### RAG as an Agent Tool

In an agent loop, RAG is exposed as a tool — the agent decides *when* to search the KB:

```python
tools = [{
    "name": "search_knowledge_base",
    "description": "Search the internal KB for known solutions. Use before answering product-specific questions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for"}
        },
        "required": ["query"]
    }
}]
```

The agent loop handles the tool call, runs `search_kb(query)`, injects the result, and the LLM reads the retrieved text in its next response. See [[Concepts/RAG - Retrieval-Augmented Generation]] for a full working agent + RAG example.

### RAG vs Web Search

Both are tools. An agent can hold both simultaneously and choose appropriately:

| | RAG (`search_knowledge_base`) | Web Search (`search_web`) |
|--|-------------------------------|--------------------------|
| Searches | Your indexed documents | The public internet |
| Speed | Milliseconds | Seconds (network call) |
| Content | Private, controlled, stable | Public, current, uncontrolled |
| Use for | Product docs, known solutions | News, live data, general facts |

---

## Tier 3: Production Patterns

### KB Document Quality Is the Bottleneck

RAG is only as good as the documents in the KB. A well-implemented retrieval system that surfaces mediocre docs produces mediocre answers. A simple system with well-written docs produces great answers.

What makes a good KB doc:
- **One issue per doc** — don't bundle multiple issues into one file
- **Structured format** — issue type, cause, fix steps, related error codes
- **Concrete fixes** — "increase 3DS timeout to 30s" beats "check gateway settings"
- **Consistent terminology** — use the same terms your team uses when talking about issues

```markdown
<!-- knowledge_base/docs/payment_e5001.md -->
# E5001 — Payment Gateway Timeout

**Issue type:** Payment failure
**Domain:** Payment | **Segment:** Top-up, Transfer

**Cause:** 3DS authentication timeout on Visa cards during high traffic.

**Fix:**
1. Increase 3DS timeout from 10s to 30s in gateway config
2. Add retry button in UI (max 3 retries)
3. Escalate to payment gateway provider if persists > 24h

**Related error codes:** E5001, E5002
```

### Testing Retrieval Quality

Before wiring RAG into the full pipeline, verify it retrieves correctly:

```python
# Create a small test set: query → expected doc
test_cases = [
    ("Visa card top-up failing with E5001", "payment_e5001.md"),
    ("QR scan not working at merchant", "qr_merchant_firmware.md"),
    ("OTP not arriving on phone", "account_otp.md"),
]

for query, expected_doc in test_cases:
    results = collection.query(
        query_embeddings=embedder.encode([query]).tolist(),
        n_results=1
    )
    top_id = results["ids"][0][0]
    passed = expected_doc in top_id
    print(f"{'✅' if passed else '❌'} '{query}' → {top_id}")
```

Run this after any change to KB docs or the embedding model.

### Metadata Filtering

ChromaDB supports filtering by metadata so you only search docs relevant to a given domain:

```python
# Index with metadata
collection.add(
    documents=["E5001 — Payment Gateway Timeout..."],
    embeddings=[...],
    ids=["payment_e5001"],
    metadatas=[{"domain": "Payment", "segment": "Top-up"}]
)

# Search only within Payment domain
results = collection.query(
    query_embeddings=embedder.encode(["Visa top-up failing"]).tolist(),
    n_results=3,
    where={"domain": "Payment"}   # ← metadata filter
)
```

Useful once the KB grows large. For a small KB (20–30 docs), filtering by distance threshold alone is sufficient.

### Persistent Storage

For production, use ChromaDB's persistent client so the index survives process restarts:

```python
# ❌ In-memory — lost on restart
db = chromadb.Client()

# ✅ Persistent — stored on disk
db = chromadb.PersistentClient(path="./chroma_db")
collection = db.get_or_create_collection("knowledge_base")
```

Index your KB docs once at setup time. At runtime, just call `collection.query()`.

---

## In Your Pipeline (Zalopay Project)

### RAG Is Stage 7, Not a Conversational Tool

In this project, RAG is not used in an agent while-loop. It's a **batch lookup step** called once per enriched item, after issue extraction:

```
Stage 5 — ISSUE EXTRACTION → "Visa card top-up failing with error E5001"
    ↓
Stage 7 — RAG LOOKUP
    embed(extracted_issue) → [0.23, -0.41, 0.88, ...]
    search ChromaDB → finds "payment_e5001.md" (L2 distance: 0.18)
    return TEXT of that doc (not the vector)
    ↓
Stage 9 — LLM REPORT receives solution text directly in its prompt
```

The solution text retrieved here flows into the report as the "Suggested Approach" column — the LLM doesn't need to invent a fix, it reads the one your team wrote.

### What Gets Embedded (Critical)

You embed the **extracted issue** from Stage 5, not the raw post text:

```python
# ❌ Poor query — noisy, multilingual, emotional
embed("Zalopay bị lỗi rồi! 😡 Không nạp tiền được bằng Visa suốt 2 tiếng!!")

# ✅ Good query — clean, technical, searchable
embed("Visa card top-up failing with error E5001 on payment screen")
```

The extracted issue is a normalized English sentence that closely matches the language your team uses in KB docs — which is also English. This alignment is intentional and improves retrieval accuracy significantly. See [[Concepts/Embeddings]] for why clean input matters for vectors.

### Distance Threshold in This Project

The pipeline uses ChromaDB's default L2 distance metric. The threshold is `< 0.5`:

```python
relevant = [doc for doc, dist in zip(docs, distances) if dist < 0.5]
if not relevant:
    return "No known solution found. Escalate to engineering team."
```

This is L2 (Euclidean) distance — **lower = more similar**. L2 `< 0.5` is roughly equivalent to cosine similarity `> 0.85` for normalized vectors. If you switch ChromaDB's collection to use cosine distance (`hnsw:space: cosine`), flip the comparison to `> 0.85`.

### KB Scope for This Project

From [[Projects/Architecture Review]], the target is **20–30 solution docs** covering:

| Domain | Example docs |
|--------|-------------|
| Payment | E5001 gateway timeout, E5002 card declined, Visa/Mastercard issues, withdrawal failures |
| QR Code | Merchant firmware, scan failures, expired QR |
| Account | OTP not arriving, login failures, registration issues |
| App Performance | Crash on launch, loading spinner stuck, UI bugs |
| Merchant | POS settlement, onboarding |

Each doc = one issue type. Write them before coding begins — the pipeline has nothing to retrieve until they exist.

### Where the Code Lives

Per [[Projects/Architecture Review]] revised file structure:

```
knowledge_base/
├── index.py     ← run once at setup: chunks and indexes all docs in docs/
├── search.py    ← search_knowledge_base(issue) called at Stage 7
└── docs/        ← 20–30 .md files your team writes
```

`search_knowledge_base()` is a shared component used by both the Jira job and the Social Media job.

---

## Related Notes

- [[Concepts/How the NLP Concepts Connect]] — how all four NLP concepts fit together in the pipeline
- [[Concepts/Memory Types]] — RAG is the "semantic memory" type
- [[Concepts/Embeddings]] — how text becomes searchable vectors; max sequence length gotcha
- [[Tools/Vector Databases]] — ChromaDB vs Pinecone vs FAISS
- [[Concepts/Tool Use & Function Calling]] — how to expose RAG as an agent tool
- [[Concepts/Agent Loop - ReAct Pattern]] — the loop RAG plugs into as a tool
- [[Projects/Pipeline Deep Dive]] — full stage-by-stage walkthrough with real examples
- [[Projects/Architecture Review]] — KB scope, file structure, and build order
