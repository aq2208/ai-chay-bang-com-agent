"""
Stage 3 — Sentiment analysis (Social Media job only).
Keeps only NEGATIVE posts. Drops positive and neutral ones.

Strategy:
  1. PhoBERT ML model (fast, free, offline) → first pass
  2. If score is borderline, LLM decides (provider set by LLM_PROVIDER in .env)
"""

from __future__ import annotations

from config import SENTIMENT_THRESHOLD
from llm_client import llm

_sentiment_pipeline = None


def _get_pipeline():
    global _sentiment_pipeline
    if _sentiment_pipeline is None:
        from transformers import pipeline as hf_pipeline
        _sentiment_pipeline = hf_pipeline(
            "text-classification",
            model="wonrax/phobert-base-vietnamese-sentiment",
        )
    return _sentiment_pipeline


def _llm_is_negative(text: str) -> bool:
    result = llm.chat(
        system="Is this text expressing a complaint or problem? Reply YES or NO only.",
        user=text,
        max_tokens=5,
    )
    return "YES" in result.upper()


def is_negative(text: str) -> bool:
    pipe = _get_pipeline()
    result = pipe(text[:512])[0]
    label: str = result["label"]
    score: float = result["score"]

    print(f"[Sentiment] PhoBERT result: label={label}, score={score:.4f} for text: {repr(text[:80])}...")

    if label == "NEG" and score >= SENTIMENT_THRESHOLD:
        print(f"[Sentiment]   => Keep: NEGATIVE (PhoBERT high confidence)")
        return True
    if label == "POS" and score >= SENTIMENT_THRESHOLD:
        print(f"[Sentiment]   => Skip: POSITIVE (PhoBERT high confidence)")
        return False
    if label == "NEU" and score >= SENTIMENT_THRESHOLD:
        print(f"[Sentiment]   => Skip: NEUTRAL (PhoBERT high confidence)")
        return False

    print(f"[Sentiment]   => Borderline/uncertain. Calling LLM fallback...")
    res = _llm_is_negative(text)
    print(f"[Sentiment]   => LLM fallback result: negative={res}")
    return res


def filter_negative(items: list[dict]) -> list[dict]:
    print(f"[Sentiment] Filtering negative items out of {len(items)} total items...")
    negatives = []
    for idx, item in enumerate(items):
        item_id = item.get("id", f"idx_{idx}")
        print(f"[Sentiment] Checking item {idx + 1}/{len(items)} (ID: {item_id})")
        if is_negative(item["text"]):
            negatives.append(item)
    print(f"[Sentiment] Filter complete. Kept {len(negatives)} negative items.")
    return negatives
