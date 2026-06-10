"""
Search the knowledge base for docs relevant to a given issue.
Requires index to be built first: .venv/bin/python knowledge_base/index.py
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from config import KB_SIMILARITY_THRESHOLD

DB_PATH     = Path(__file__).parent.parent / "chroma_db"
COLLECTION  = "knowledge_base"
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

_model:      SentenceTransformer | None = None
_collection = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(DB_PATH))
        _collection = client.get_collection(COLLECTION)
    return _collection


def search(issue: str, top_k: int = 2) -> list[dict]:
    """
    Find the most relevant KB docs for an issue string.

    Args:
        issue: extracted issue sentence (English)
        top_k: maximum number of results to return

    Returns:
        List of matches above KB_SIMILARITY_THRESHOLD, each:
        {"text": str, "filename": str, "similarity": float}
        Empty list if nothing matches.
    """
    col       = _get_collection()
    embedding = _get_model().encode([issue]).tolist()

    results = col.query(
        query_embeddings=embedding,
        n_results=min(top_k, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    matches = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        # cosine space: distance = 1 − similarity  →  similarity = 1 − distance
        similarity = round(1.0 - dist, 4)
        if similarity >= KB_SIMILARITY_THRESHOLD:
            matches.append({
                "text":       doc,
                "filename":   meta.get("filename", ""),
                "similarity": similarity,
            })

    return matches


def get_suggested_approach(issue: str) -> str:
    """
    Convenience function used by the pipeline.
    Returns the "Suggested Approach" section text from the best matching doc.
    Falls back to a standard escalation message if nothing matches.
    """
    matches = search(issue)
    if not matches:
        return "No known solution found. Escalate to engineering team for investigation."

    texts = []
    for m in matches:
        doc_text = m["text"]
        if "## Suggested Approach" in doc_text:
            # Each chunk covers one issue — take the first (only) Suggested Approach
            section = doc_text.split("## Suggested Approach")[1].strip()
            # Stop at the next heading if any
            if "\n##" in section:
                section = section[: section.index("\n##")].strip()
            texts.append(section)
        else:
            texts.append(doc_text[:600])

    return "\n\n".join(texts)
