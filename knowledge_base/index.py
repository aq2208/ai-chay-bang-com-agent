"""
Build the ChromaDB knowledge base index from knowledge_base/docs/.

Each .md file is split by '---' separators into individual issue chunks.
This gives more accurate search — each chunk covers exactly one issue type.

Run once (or re-run whenever docs change):
    .venv/bin/python knowledge_base/index.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

DOCS_DIR    = Path(__file__).parent / "docs"
DB_PATH     = Path(__file__).parent.parent / "chroma_db"
COLLECTION  = "knowledge_base"
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


def _split_into_chunks(text: str, stem: str) -> list[tuple[str, str, dict]]:
    """
    Split a doc by '---' separators into chunks.
    Each chunk becomes one searchable entry in ChromaDB.

    Returns list of (chunk_id, chunk_text, metadata).
    """
    # Split on lines containing only dashes (markdown horizontal rule)
    sections = re.split(r"\n\s*---+\s*\n", text)
    chunks = []
    for i, section in enumerate(sections):
        section = section.strip()
        # Only index sections that contain actual solutions (not header/metadata blocks)
        if "## Suggested Approach" not in section:
            continue
        if len(section.split()) < 10:
            continue
        chunk_id = f"{stem}_{i}"
        heading_match = re.search(r"^#{1,3} (.+)$", section, re.MULTILINE)
        title = heading_match.group(1).strip() if heading_match else stem
        chunks.append((chunk_id, section, {"filename": f"{stem}.md", "stem": stem, "title": title}))
    return chunks


def build_index() -> int:
    """
    Read all .md / .txt files from docs/, split into chunks, embed, store in ChromaDB.
    Drops the existing collection first so re-runs are always a clean rebuild.

    Returns:
        Number of chunks indexed (0 if docs/ is empty).
    """
    model  = SentenceTransformer(EMBED_MODEL)
    client = chromadb.PersistentClient(path=str(DB_PATH))

    # Clean rebuild — drop old collection if it exists
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass

    collection = client.create_collection(
        COLLECTION,
        metadata={"hnsw:space": "cosine"},  # distances in [0,1]: 0=identical
    )

    doc_paths = sorted(DOCS_DIR.glob("*.md")) + sorted(DOCS_DIR.glob("*.txt"))
    if not doc_paths:
        print(f"No docs found in {DOCS_DIR}. Add .md files and re-run.")
        return 0

    ids, texts, metadatas = [], [], []
    for path in doc_paths:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        for chunk_id, chunk_text, meta in _split_into_chunks(raw, path.stem):
            ids.append(chunk_id)
            texts.append(chunk_text)
            metadatas.append(meta)

    if not texts:
        return 0

    embeddings = model.encode(texts, show_progress_bar=False).tolist()
    collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    print(f"Indexed {len(texts)} chunks from {len(doc_paths)} docs → ChromaDB at {DB_PATH}")
    for stem in sorted({m["stem"] for m in metadatas}):
        count = sum(1 for m in metadatas if m["stem"] == stem)
        print(f"  • {stem}.md  ({count} chunks)")
    return len(texts)


if __name__ == "__main__":
    count = build_index()
    sys.exit(0 if count > 0 else 1)
