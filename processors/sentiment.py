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

    if label == "NEG" and score >= SENTIMENT_THRESHOLD:
        return True
    if label == "POS" and score >= SENTIMENT_THRESHOLD:
        return False
    if label == "NEU" and score >= SENTIMENT_THRESHOLD:
        return False

    return _llm_is_negative(text)


def filter_negative(items: list[dict]) -> list[dict]:
    return [item for item in items if is_negative(item["text"])]
