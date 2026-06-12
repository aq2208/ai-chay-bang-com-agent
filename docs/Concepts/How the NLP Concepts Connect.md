# How the NLP Concepts Connect

#concept #nlp #overview

> [!note] Project stack: PhoBERT (sentiment) + MiniLM embeddings + ChromaDB, with **`google/gemma-4-31b-it`
> via AgentBase MaaS** for all LLM steps. Canonical design: [[Projects/00 - Project Home]].

---

## The Short Answer

You never pass tokenizer output directly to embeddings. Both the sentiment model and the embedding model have their own internal tokenizers — you just pass clean text to each of them.

The four concepts are **not a linear chain**. They're two parallel branches that diverge after preprocessing:

```
Raw post: "Zalopay bị lỗi rồi!!!! 😡 http://fb.com/123"
    │
    ▼
① TOKENIZATION / PREPROCESSING  (Stage 1)
   clean_text() — remove URLs, emoji, normalize Unicode
   Output: "zalopay bị lỗi rồi!"
    │
    │  ← this clean text string is what everything else receives
    │
    ├──────────────────────────────────────────┐
    ▼                                          │
② SENTIMENT ANALYSIS  (Stage 3)               │
   PhoBERT reads clean text                    │
   (uses its own internal BPE tokenizer)       │
   Output: NEG 0.94 → keep this post           │
    │                                          │
    ▼                                          │
   LLM ISSUE EXTRACTION  (Stage 5)             │
   Claude Haiku reads clean text               │
   Output: "Visa card top-up failing           │
            with error E5001"   ◄──────────────┘
    │
    │  ← this extracted issue is what gets embedded, NOT the Stage 1 output
    │
    ├──────────────────────────────┐
    ▼                              ▼
③ EMBEDDINGS (Stage 7 — RAG)   ③ EMBEDDINGS (Stage 8 — Grouping)
   embed(extracted_issue)          embed(all extracted issues)
   → vector for searching          → vectors for clustering
    │
    ▼
④ RAG  (Stage 7)
   search ChromaDB with that vector
   → retrieve solution TEXT (not the vector)
   → inject into LLM report prompt
```

---

## Three Things to Internalize

### 1. Preprocessing produces clean text, not tokens

The word "tokenization" in the doc title just means cleaning. Its output is still a plain string — `"zalopay bị lỗi rồi!"`. Every downstream model tokenizes that string internally. You never manually split text into tokens for any step in this pipeline.

### 2. Embeddings receive the extracted issue, not the cleaned post

This is the most important one. You don't embed `"zalopay bị lỗi rồi!"`. You embed `"Visa card top-up failing with error E5001"` — the clean, English, technical statement produced by Claude Haiku at Stage 5.

```python
# ❌ What seems logical but is wrong
embed("zalopay bị lỗi rồi!")

# ✅ What actually happens in the pipeline
embed("Visa card top-up failing with error E5001")
```

The extracted issue is normalized, language-consistent, and technically precise. It closely matches the language in your KB docs (also English), which is why RAG retrieval works. See [[Concepts/Embeddings]] for why input quality matters so much for vectors.

### 3. Sentiment Analysis and Embeddings are parallel, not sequential

Sentiment Analysis filters *which* posts survive to the next stage. Embeddings process *what the surviving posts mean*. One doesn't feed the other — both just need clean text from Stage 1.

```
Preprocessing → Sentiment Analysis → (post survives)
                                            ↓
                               Issue Extraction (LLM)
                                            ↓
                               Embeddings → RAG
```

---

## What Each Model Tokenizes Internally

You pass a clean text string to each model. The tokenization is invisible to you:

| Step | Model | Internal tokenizer | Input you provide |
|------|-------|-------------------|------------------|
| Stage 3 | PhoBERT (sentiment) | SentencePiece BPE | clean text string |
| Stage 7–8 | `paraphrase-multilingual-MiniLM-L12-v2` | WordPiece | extracted issue string |
| Stage 5, 9 | Claude (LLM) | Anthropic BPE | clean text string |

The only reason to think about tokens at all:
- **PhoBERT caps at 512 tokens** → handled with `text[:512]`
- **Embedding model caps at 128 tokens** → handled with `chunk_text()`
- **LLM costs money per token** → preprocessing reduces token count and cost

---

## Do You Need Manual Tokenization?

No. In this project, "tokenization" means `clean_text()`. You're already doing it.

You would need manual tokenization only for classical ML pipelines (TF-IDF, bag-of-words, n-grams) where you build features from word counts. None of those techniques are used here — every model in this pipeline is a neural network that reads raw text.

---

## Related Notes

- [[Concepts/Tokenization & Text Preprocessing]] — Stage 1: cleaning raw text
- [[Concepts/Sentiment Analysis]] — Stage 3: filtering negative posts
- [[Concepts/Embeddings]] — Stage 7–8: converting extracted issues to vectors
- [[Concepts/RAG - Retrieval-Augmented Generation]] — Stage 7: searching KB with vectors
- [[Projects/Pipeline Deep Dive]] — full code walkthrough of every stage
