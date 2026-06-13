"""
Dynamic issues store — powers the agentic Q&A surface.

After each pipeline run, the grouped/enriched issues are indexed into an 'issues'
ChromaDB collection (separate from the static solution 'knowledge_base' and 'taxonomy'
collections). A Product Owner can then ask free-form questions and get an answer grounded
in the actual indexed issues:

    {"action": "query", "question": "summarize payment issues this week"}

Persistence note: this collection lives on the container's local disk. It persists while a
runtime replica stays warm but resets on redeploy/scale-down — fine for a demo (run jobs,
then query in the same session). Upgrade path: AgentBase Memory / Knowledge Base.
"""

from __future__ import annotations

import hashlib
from datetime import date as _date
from pathlib import Path

import chromadb

from knowledge_base.search import _get_model  # reuse the one loaded MiniLM embedder
from llm_client import llm

DB_PATH    = Path(__file__).parent.parent / "chroma_db"
COLLECTION = "issues"

_client = None


def _get_collection():
    """get-or-create the writable issues collection."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(DB_PATH))
    return _client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


def index_issues(items: list[dict], job_name: str, run_date: str | None = None) -> int:
    """
    Upsert grouped/enriched issues into the issues collection.
    Called at the end of each job run. Best-effort — callers should not let a failure
    here abort report delivery.

    Args:
        items:    grouped pipeline items (need at least "extracted_issue")
        job_name: e.g. "Jira" / "Social Media"
        run_date: ISO date string; defaults to today

    Returns:
        Number of issues indexed.
    """
    items = [i for i in items if i.get("extracted_issue")]
    if not items:
        return 0

    run_date = run_date or _date.today().isoformat()
    col = _get_collection()

    ids, docs, metas = [], [], []
    for item in items:
        issue = item["extracted_issue"]
        # Stable per-day id so re-running a job updates rather than duplicates.
        digest = hashlib.md5(issue.lower().encode("utf-8")).hexdigest()[:12]
        ids.append(f"{run_date}_{digest}")
        docs.append(issue)
        metas.append({
            "issue":    issue,
            "domain":   item.get("domain", "Other"),
            "segment":  item.get("segment", "General"),
            "mentions": int(item.get("mentions", 1)),
            "sources":  item.get("sources", item.get("source", "unknown")),
            "job":      job_name,
            "date":     run_date,
        })

    embeddings = _get_model().encode(docs).tolist()
    col.upsert(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
    return len(ids)


_ANSWER_SYSTEM = (
    "You are a Zalopay product analytics assistant answering a Product Owner's question.\n"
    "Answer ONLY from the retrieved issues provided below — do not invent issues or numbers.\n"
    "Be concise and factual. Where useful, cite mention counts, sources, and dates.\n"
    "If none of the retrieved issues are relevant to the question, say so plainly."
)


def answer_question(question: str, top_k: int = 10) -> str:
    """RAG over the issues store → grounded natural-language answer."""
    col = _get_collection()
    if col.count() == 0:
        return ("No issues have been indexed yet. Run a pipeline job first "
                "(e.g. {\"action\":\"run\",\"job\":\"all\"}), then ask again.")

    embedding = _get_model().encode([question]).tolist()
    results = col.query(
        query_embeddings=embedding,
        n_results=min(top_k, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    lines = []
    for meta in results["metadatas"][0]:
        lines.append(
            f"- [{meta.get('date','?')}] {meta.get('domain','?')}/{meta.get('segment','?')}: "
            f"{meta.get('issue','')} "
            f"(mentions: {meta.get('mentions','?')}, sources: {meta.get('sources','?')}, "
            f"job: {meta.get('job','?')})"
        )
    context = "\n".join(lines)

    return llm.chat(
        system=_ANSWER_SYSTEM,
        user=f"Question: {question}\n\nRetrieved issues:\n{context}",
        max_tokens=500,
        fast=False,
    )
