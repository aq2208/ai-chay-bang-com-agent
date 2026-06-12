# Vector Databases

#tool

---

## What They Do

Store text as numerical vectors (embeddings) so you can search by *meaning*, not just keywords. Essential for RAG.

See [[Concepts/RAG - Retrieval-Augmented Generation]] for the full RAG pattern.

---

## Option 1: ChromaDB (Best for Hackathon)

Local, free, zero infrastructure, runs in-process. Perfect for hackathons.

```bash
pip install chromadb
```

```python
import chromadb

# In-memory (fast, lost on restart)
client = chromadb.Client()

# Persistent (survives restarts, stored on disk)
client = chromadb.PersistentClient(path="./my_vector_db")

# Create a collection (like a table)
collection = client.create_collection("knowledge_base")

# Add documents (ChromaDB embeds them automatically with a default model)
collection.add(
    documents=["Hanoi is the capital of Vietnam", "Ho Chi Minh City is in the south"],
    ids=["doc1", "doc2"]
)

# Query by meaning
results = collection.query(
    query_texts=["What's the capital?"],
    n_results=2
)
print(results["documents"])
```

### With Custom Embeddings

```python
from sentence_transformers import SentenceTransformer

embedder = SentenceTransformer("all-MiniLM-L6-v2")  # local, free

# Embed and add
docs = ["Hanoi is the capital", "HCMC is in the south"]
embeddings = embedder.encode(docs).tolist()

collection.add(
    documents=docs,
    embeddings=embeddings,
    ids=["doc1", "doc2"],
    metadatas=[{"source": "wiki"}, {"source": "wiki"}]  # optional metadata
)

# Query
q_embedding = embedder.encode(["northern city"]).tolist()
results = collection.query(query_embeddings=q_embedding, n_results=2)
```

---

## Option 2: Pinecone (Cloud, Production)

Hosted vector DB. Scales to millions of vectors. Needs an account.

```bash
pip install pinecone-client
```

```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="your-api-key")

# Create index
pc.create_index(
    name="my-index",
    dimension=384,         # must match your embedding model's output size
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1")
)

index = pc.Index("my-index")

# Upsert vectors
index.upsert(vectors=[
    ("doc1", [0.1, 0.2, ...], {"text": "Hanoi is the capital"}),
    ("doc2", [0.3, 0.1, ...], {"text": "HCMC is in the south"}),
])

# Query
results = index.query(vector=[0.1, 0.2, ...], top_k=3, include_metadata=True)
```

---

## Option 3: FAISS (Facebook, Local, Fast)

Ultra-fast, runs locally, but no persistence by default (save/load manually).

```bash
pip install faiss-cpu
```

```python
import faiss
import numpy as np

# Create index
dimension = 384
index = faiss.IndexFlatL2(dimension)

# Add vectors
vectors = np.array([[...], [...]], dtype="float32")
index.add(vectors)

# Search
query = np.array([[...]], dtype="float32")
distances, indices = index.search(query, k=3)  # k = top 3 results
```

---

## Embedding Models

The model that turns text → vectors. These run locally for free:

| Model | Dimensions | Speed | Quality |
|-------|------------|-------|---------|
| `all-MiniLM-L6-v2` | 384 | Fast | Good |
| `all-mpnet-base-v2` | 768 | Medium | Better |
| `text-embedding-3-small` | 1536 | API call | Best (OpenAI) |

```bash
pip install sentence-transformers
```

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
embedding = model.encode("Hello world")  # → numpy array of 384 floats
```

---

## Comparison

| | ChromaDB | Pinecone | FAISS |
|--|----------|----------|-------|
| Setup | Instant | Account needed | Instant |
| Cost | Free | Free tier | Free |
| Persistence | Yes | Yes (cloud) | Manual |
| Scale | Small-medium | Millions | Large |
| Best for | Hackathon ✅ | Production | Research |

---

## Related Notes

- [[Concepts/RAG - Retrieval-Augmented Generation]] — how to use these in a RAG pipeline
- [[Concepts/Memory Types]] — vector DBs are "semantic memory"
