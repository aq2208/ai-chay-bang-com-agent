"""
Stage 7 — Semantic grouping.
Merges near-duplicate issues using cosine similarity of their embeddings.

Why this matters:
  - 7 people complaining about "Visa top-up failing" should appear as ONE row
    with mentions=7, not 7 separate rows in the report.
  - Reduces report noise and highlights the most impactful issues.

Input:  list of enriched items — each must have "extracted_issue" field
Output: deduplicated list sorted by mentions (highest first)
        each item gains: mentions (int), sources (str), ids (list)
"""

from __future__ import annotations

import numpy as np

from config import GROUPING_THRESHOLD

EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(EMBED_MODEL)
    return _embedder


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def group_similar(items: list[dict], threshold: float | None = None) -> list[dict]:
    """
    Greedy cosine-similarity clustering on the "extracted_issue" field.

    Args:
        items:     list of enriched pipeline items (must have "extracted_issue")
        threshold: override GROUPING_THRESHOLD from config

    Returns:
        Deduplicated list. Each item has extra fields:
            mentions (int)  — how many original items were merged into this group
            sources  (str)  — comma-separated unique source names
            ids      (list) — all original item IDs in this group
        Sorted by mentions descending (most-reported issue first).
    """
    if not items:
        print("[Grouper] No items to group.")
        return []

    cutoff  = threshold if threshold is not None else GROUPING_THRESHOLD
    print(f"[Grouper] Starting grouping on {len(items)} items using threshold={cutoff:.4f}...")
    issues  = [item["extracted_issue"] for item in items]
    
    print(f"[Grouper] Generating sentence embeddings using model '{EMBED_MODEL}'...")
    vectors = _get_embedder().encode(issues)  # shape (N, dim)

    used:   set[int]    = set()
    groups: list[dict]  = []

    for i, vi in enumerate(vectors):
        if i in used:
            continue

        cluster = [items[i]]
        used.add(i)
        
        rep_issue = items[i]["extracted_issue"]
        print(f"[Grouper]   New group representative: (ID: {items[i]['id']}) '{rep_issue}'")

        for j, vj in enumerate(vectors):
            if j not in used:
                sim = _cosine(vi, vj)
                other_issue = items[j]["extracted_issue"]
                if sim >= cutoff:
                    print(f"[Grouper]     => Merging with (ID: {items[j]['id']}) '{other_issue}' (similarity={sim:.4f} >= threshold)")
                    cluster.append(items[j])
                    used.add(j)
                else:
                    # Optional log for close issues, but let's log any similarity above 0.3 for visibility
                    if sim >= 0.3:
                        print(f"[Grouper]     - Check (ID: {items[j]['id']}) '{other_issue}' (similarity={sim:.4f} < threshold, skip)")

        # Representative = first item in cluster; add aggregated metadata
        rep = cluster[0].copy()
        rep["mentions"] = len(cluster)
        rep["sources"]  = ", ".join(sorted({c["source"] for c in cluster}))
        rep["ids"]      = [c["id"] for c in cluster]
        
        post_urls = []
        all_images = []
        for c in cluster:
            url = c.get("post_url")
            if url and url not in post_urls:
                post_urls.append(url)
            
            imgs = c.get("images") or []
            if isinstance(imgs, str):
                imgs = [imgs]
            for img in imgs:
                if img and img not in all_images:
                    all_images.append(img)
        
        rep["post_urls"] = post_urls
        rep["all_images"] = all_images
        groups.append(rep)
        print(f"[Grouper]   Group finished with {len(cluster)} mentions. IDs: {rep['ids']}")

    sorted_groups = sorted(groups, key=lambda x: x["mentions"], reverse=True)
    print(f"[Grouper] Grouping completed. Grouped {len(items)} items into {len(sorted_groups)} distinct issue group(s).")
    return sorted_groups
