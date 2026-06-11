"""
Build the ChromaDB indexes from knowledge_base/docs/.

Two collections are produced:
  • "knowledge_base" — solution docs. Each .md is split by '---' into issue chunks;
    only chunks with a "## Suggested Approach" are indexed (used for RAG solution lookup).
    Each chunk carries its file-level **Domain:** in metadata.
  • "taxonomy"       — built from docs/taxonomy.md. One chunk per domain/segment with a
    definition + example phrasings, each tagged with domain + segment metadata. Used by the
    classifier to ground domain/segment decisions in real examples.

Run once (or re-run whenever docs change):
    .venv/bin/python knowledge_base/index.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

DOCS_DIR            = Path(__file__).parent / "docs"
TAXONOMY_FILE       = DOCS_DIR / "taxonomy.md"
DB_PATH             = Path(__file__).parent.parent / "chroma_db"
COLLECTION          = "knowledge_base"
TAXONOMY_COLLECTION = "taxonomy"
EMBED_MODEL         = "paraphrase-multilingual-MiniLM-L12-v2"


def _parse_field(text: str, field: str) -> str:
    """Extract a `**Field:** value` line value from a markdown block (empty if absent)."""
    m = re.search(rf"^\*\*{re.escape(field)}:\*\*\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _split_solution_chunks(text: str, stem: str) -> list[tuple[str, str, dict]]:
    """
    Split a solution doc by '---' into chunks. Only index chunks that contain an actual
    solution ('## Suggested Approach'). Each chunk inherits the file-level Domain.

    Returns list of (chunk_id, chunk_text, metadata).
    """
    domain = _parse_field(text, "Domain")  # from the file header block
    sections = re.split(r"\n\s*---+\s*\n", text)
    chunks = []
    for i, section in enumerate(sections):
        section = section.strip()
        if "## Suggested Approach" not in section:
            continue
        if len(section.split()) < 10:
            continue
        chunk_id = f"{stem}_{i}"
        heading_match = re.search(r"^#{1,3} (.+)$", section, re.MULTILINE)
        title = heading_match.group(1).strip() if heading_match else stem
        chunks.append((
            chunk_id,
            section,
            {"filename": f"{stem}.md", "stem": stem, "title": title, "domain": domain},
        ))
    return chunks


def _split_taxonomy_chunks(text: str) -> list[tuple[str, str, dict]]:
    """
    Split taxonomy.md by '---'. Index every section that declares a **Domain:** and
    **Segment:**, tagging it with those values.

    Returns list of (chunk_id, chunk_text, metadata).
    """
    sections = re.split(r"\n\s*---+\s*\n", text)
    chunks = []
    for i, section in enumerate(sections):
        section = section.strip()
        domain  = _parse_field(section, "Domain")
        segment = _parse_field(section, "Segment")
        if not domain or not segment:
            continue
        chunks.append((
            f"tax_{i}",
            section,
            {"domain": domain, "segment": segment},
        ))
    return chunks


def _rebuild_collection(client, model, name: str, ids, texts, metadatas) -> int:
    try:
        client.delete_collection(name)
    except Exception:
        pass
    if not texts:
        return 0
    collection = client.create_collection(name, metadata={"hnsw:space": "cosine"})
    embeddings = model.encode(texts, show_progress_bar=False).tolist()
    collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    return len(texts)


def build_index() -> int:
    """
    Build the solution ('knowledge_base') and 'taxonomy' collections in ChromaDB.
    Both are clean rebuilds. Returns the number of solution chunks indexed.
    """
    model  = SentenceTransformer(EMBED_MODEL)
    client = chromadb.PersistentClient(path=str(DB_PATH))

    # ── Solution collection (exclude taxonomy.md) ──────────────────────────
    doc_paths = [
        p for p in sorted(DOCS_DIR.glob("*.md")) + sorted(DOCS_DIR.glob("*.txt"))
        if p.name != TAXONOMY_FILE.name
    ]
    ids, texts, metadatas = [], [], []
    for path in doc_paths:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        for chunk_id, chunk_text, meta in _split_solution_chunks(raw, path.stem):
            ids.append(chunk_id)
            texts.append(chunk_text)
            metadatas.append(meta)
    n_solution = _rebuild_collection(client, model, COLLECTION, ids, texts, metadatas)

    # ── Taxonomy collection ────────────────────────────────────────────────
    n_tax = 0
    if TAXONOMY_FILE.exists():
        tax_raw = TAXONOMY_FILE.read_text(encoding="utf-8").strip()
        t_ids, t_texts, t_meta = [], [], []
        for cid, ctext, meta in _split_taxonomy_chunks(tax_raw):
            t_ids.append(cid)
            t_texts.append(ctext)
            t_meta.append(meta)
        n_tax = _rebuild_collection(client, model, TAXONOMY_COLLECTION, t_ids, t_texts, t_meta)

    if n_solution == 0:
        print(f"No solution chunks found in {DOCS_DIR}. Add .md files and re-run.")
    else:
        print(f"Indexed {n_solution} solution chunks from {len(doc_paths)} docs → {DB_PATH}")
        for stem in sorted({m["stem"] for m in metadatas}):
            count = sum(1 for m in metadatas if m["stem"] == stem)
            domain = next((m["domain"] for m in metadatas if m["stem"] == stem), "")
            print(f"  • {stem}.md  ({count} chunks, domain={domain or '?'})")
    print(f"Indexed {n_tax} taxonomy chunks → '{TAXONOMY_COLLECTION}' collection")

    return n_solution


if __name__ == "__main__":
    count = build_index()
    sys.exit(0 if count > 0 else 1)
