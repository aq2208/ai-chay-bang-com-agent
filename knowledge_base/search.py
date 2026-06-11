"""
Search the knowledge base for docs relevant to a given issue.
Requires indexes to be built first: .venv/bin/python knowledge_base/index.py

Two retrievers:
  • search()          — solution chunks ('knowledge_base' collection) for RAG solution lookup.
  • search_taxonomy() — domain/segment taxonomy chunks ('taxonomy' collection) for grounding
                        classification. Supports an optional domain filter.
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from config import KB_SIMILARITY_THRESHOLD

DB_PATH             = Path(__file__).parent.parent / "chroma_db"
COLLECTION          = "knowledge_base"
TAXONOMY_COLLECTION = "taxonomy"
EMBED_MODEL         = "paraphrase-multilingual-MiniLM-L12-v2"

_model:       SentenceTransformer | None = None
_client = None
_collections: dict[str, object] = {}


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def _get_collection(name: str = COLLECTION):
    """Return a cached ChromaDB collection by name (None if it doesn't exist)."""
    global _client
    if name not in _collections:
        if _client is None:
            _client = chromadb.PersistentClient(path=str(DB_PATH))
        try:
            _collections[name] = _client.get_collection(name)
        except Exception:
            _collections[name] = None
    return _collections[name]


def search(issue: str, top_k: int = 2) -> list[dict]:
    """
    Find the most relevant solution chunks for an issue string.

    Returns matches above KB_SIMILARITY_THRESHOLD, each:
        {"text": str, "filename": str, "domain": str, "similarity": float}
    Empty list if nothing matches or the index is missing.
    """
    col = _get_collection(COLLECTION)
    if col is None or col.count() == 0:
        return []

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
                "domain":     meta.get("domain", ""),
                "similarity": similarity,
            })
    return matches


def search_taxonomy(issue: str, top_k: int = 5, domain: str | None = None) -> list[dict]:
    """
    Retrieve taxonomy entries most similar to an issue, for grounding classification.

    Args:
        issue:  the extracted issue sentence
        top_k:  max entries to return
        domain: if given, restrict to that domain's segments (used for segment classification)

    Returns:
        List of {"text", "domain", "segment", "similarity"} sorted by similarity desc.
        Empty list if the taxonomy collection is missing. No similarity floor — these are
        few-shot grounding hints, not authoritative matches.
    """
    col = _get_collection(TAXONOMY_COLLECTION)
    if col is None or col.count() == 0:
        return []

    embedding = _get_model().encode([issue]).tolist()
    kwargs = {
        "query_embeddings": embedding,
        "n_results": min(top_k, col.count()),
        "include": ["documents", "metadatas", "distances"],
    }
    if domain:
        kwargs["where"] = {"domain": domain}

    results = col.query(**kwargs)
    matches = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        matches.append({
            "text":       doc,
            "domain":     meta.get("domain", ""),
            "segment":    meta.get("segment", ""),
            "similarity": round(1.0 - dist, 4),
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
