# Processors

This directory contains the sequential data processing stages (pipeline processors) used to clean, analyze, enrich, and group user feedback.

## Pipeline Stages

- **[preprocessor.py](./preprocessor.py)** (Stage 1 & 2): Cleans raw text (removes URLs, hashtags, mentions, emojis), drops short posts, and deduplicates based on content fingerprint.
- **[sentiment.py](./sentiment.py)** (Stage 3): Filters out positive/neutral posts to keep only complaints. Uses PhoBERT offline with LLM fallback for borderline cases.
- **[image_analyzer.py](./image_analyzer.py)** (Stage 4): Uses Vision LLM to analyze screenshot attachments, matching them against known templates in `sample_images/<Domain>/`.
- **[issue_extractor.py](./issue_extractor.py)** (Stage 5): Converts noisy multi-lingual text and image descriptions into a single concise English technical issue statement.
- **[classifier.py](./classifier.py)** (Stage 6): RAG-grounded classification of issues into specific domains and segments (validated against `config.py` domains/segments).
- **[grouper.py](./grouper.py)** (Stage 7): Clusters near-duplicate issues using sentence embeddings (`paraphrase-multilingual-MiniLM-L12-v2`) and cosine similarity.

## Running Tests

Verify the processors by running the Phase unit tests:
```bash
python test_phase2.py   # Tests preprocessor, sentiment, extractor, and classifier
python test_phase4.py   # Tests image analyzer and semantic grouper
```
