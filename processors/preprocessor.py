"""
Stage 1 — Text preprocessing.
Cleans raw text before any ML or LLM step runs on it.
No API calls. No models. Pure string operations.
"""

import re


def clean_text(text: str) -> str:
    """Remove URLs, hashtags, mentions, emoji, and normalize whitespace."""
    text = re.sub(r'http\S+', '', text)                  # remove URLs
    text = re.sub(r'#\w+', '', text)                      # remove #hashtags
    text = re.sub(r'@\w+', '', text)                      # remove @mentions
    # Keep Vietnamese characters (À-ɏ, Ḁ-ỿ range) and basic Latin; drop emoji/symbols
    text = re.sub(r'[^\w\sÀ-ɏḀ-ỿ\-]', ' ', text)
    text = re.sub(r'[!?]{2,}', '!', text)                # normalize !!! → !
    text = re.sub(r'\s+', ' ', text).strip()             # collapse whitespace
    return text


def is_meaningful(text: str, min_words: int = 4) -> bool:
    """Drop posts too short to contain useful information."""
    return len(text.split()) >= min_words


def deduplicate(items: list[dict]) -> list[dict]:
    """Remove near-identical items using the first 80 characters as a fingerprint."""
    seen: set[str] = set()
    unique: list[dict] = []
    for item in items:
        key = item["text"][:80].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def preprocess(items: list[dict]) -> list[dict]:
    """
    Full preprocessing pipeline:
      clean → filter short → deduplicate
    Returns a new list of items with cleaned text.
    Original items are not mutated.
    """
    cleaned = []
    for item in items:
        text = clean_text(item["text"])
        if is_meaningful(text):
            cleaned.append({**item, "text": text})

    return deduplicate(cleaned)
