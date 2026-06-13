# Project Context — Zalopay Issue Analytics Agent

#project

> [!note] Canonical hub: **[[Projects/00 - Project Home]]**. This page is narrative background;
> the homepage holds the authoritative design, tech stack, and build status.

> [!warning] Rewritten 2026-06-11. The previous version described **OpenAI GPT-4o / `text-embedding-3-small`
> / underthesea / Medallion Gold** — that LLM/embedding stack is obsolete (the real system uses Gemma via
> AgentBase MaaS + MiniLM). **However, its crawling description was right:** the Threads crawler really is
> **Playwright public keyword search + base64 images + a Bronze `.jsonl` layer with MD5 dedup**. See
> "Data crawling" below.

---

## Overview

An enterprise-style **AI Data Analytics Agent** for Product Owners and dev teams in FinTech / e-wallet
(Zalopay). It automates collecting, filtering, and analyzing user feedback from multiple sources, and
condenses it into high-quality issue reports with concrete suggested solutions.

### Core goals
- **Multi-source ingestion** — internal (Jira tickets) + public social media (Facebook, Threads).
- **Intelligent filtering** — keep only negative records (complaints, bug reports, transaction errors); drop spam, ads, praise.
- **Domain classification** — pinpoint which part of the system the issue belongs to (Payment, QR Code, Account, App Performance, Merchant, Other), grounded by RAG against a taxonomy + knowledge base.
- **Suggested solutions** — generate a structured report for the PO and propose technical handling for the dev team, retrieved from the team's solution knowledge base.
- **Agentic Q&A** — a PO can ask free-form questions (e.g. "summarize payment issues this week") and get answers grounded in the indexed issues.

---

## Decoupled jobs

Two independent jobs that can run, fail, and be triggered independently:

- **Job 1 — Jira:** fetch tickets via REST API (JQL) → preprocess → extract → RAG-grounded classify → group → KB solution lookup → report.
- **Job 2 — Social Media:** fetch Facebook + Threads by keyword → preprocess → sentiment filter (PhoBERT, keep negatives) → image analysis (Gemma vision) → extract → classify → group → KB lookup → report.

Both share the same downstream stages. Full diagram: [[Projects/Architecture]]. Stage-by-stage rationale:
[[Projects/Pipeline Deep Dive]].

---

## Data crawling (Bronze layer)

Crawling is **decoupled** from the agent and runs **offline** (Colab / a worker / locally) — it does
not run inside the AgentBase `/invocations` runtime. Crawlers write raw records to
`data/raw/<source>_<ts>.jsonl` (the **Bronze** layer); the agent's connectors read the latest bronze
file and normalize it into pipeline items.

- **Threads** — `crawlers/threads_crawler.py`: **Playwright** drives headless Chromium against
  `threads.net/search?q=<keyword>` (public keyword search), filters by post age, downloads attached
  images and stores them **inline as base64 data URIs**, dedups by MD5 content hash, writes
  `data/raw/threads_<ts>.jsonl` (rich `SocialPost` schema). `connectors/threads.py` reads it.
- **Why offline:** headless Chromium is heavy and gets blocked from datacenter IPs; a multi-minute
  scroll-crawl would also exceed the invocation timeout. Bronze `.jsonl` is the hand-off (delivery to the
  deployed agent — object storage / payload — is a later decision; local files for now).
- Facebook/Jira follow the same bronze convention (`crawlers/bronze.py` is the shared JSONL IO).

## How it runs (AgentBase)

A **Custom Agent** on VNG AgentBase: a single `greennode-agentbase` entrypoint at `POST /invocations`
dispatches on `payload["action"]` — `run` (execute a job) or `query` (agentic Q&A). The only LLM is
**`google/gemma-4-31b-it`** via the OpenAI-compatible MaaS endpoint. PhoBERT, MiniLM embeddings, and the
ChromaDB index are baked into the Docker image and run on a 4CPU/8GB runtime. See
[[Tools/AgentBase Platform Guide]] and [[Projects/00 - Project Home]] for the deployment shape.

---

## Data schemas (illustrative)

Pipeline items are plain dicts: `{id, source, text, images, timestamp}`. After enrichment they gain
`extracted_issue`, `domain`, `segment`, `mentions`, `sources`, and a retrieved `suggested_approach`.

Domains/segments are defined in `clawathon-aicbc-agent/config.py` and grounded by
`knowledge_base/docs/taxonomy.md`.

---

## Related

- [[Projects/00 - Project Home]] · [[Projects/Hackathon]] · [[Projects/Architecture]] · [[Projects/Code Walkthrough]]
