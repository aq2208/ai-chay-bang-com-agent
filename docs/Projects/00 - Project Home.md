# 🏦 ZaloPay Issue Analytics Agent — Project Home

#project #home

> **The single source of truth for this project.** Every other project doc links back here.
> If something elsewhere contradicts this page, this page wins — fix the other doc.

**Last updated:** 2026-06-11 · **Event:** VNG AI-Agent Hackathon (7 days) · **Platform:** VNG AgentBase

---

## 1. What we're building

An **AI Voice-of-Customer (VoC) analytics agent** for ZaloPay (FinTech / e-wallet). It ingests user
complaints from **Jira + Facebook + Threads**, filters and enriches them, and produces **structured
issue reports with suggested solutions** for Product Owners — plus an **agentic Q&A** surface where a PO
can ask free-form questions and get answers grounded in the indexed issues.

Two deliverables from one agent:
1. **Issue reports** — per run, a markdown table: Domain · Segment · Issue · Mentions · Sources · Suggested Approach.
2. **Q&A** — e.g. *"summarize payment issues this week"* → grounded natural-language answer.

It is a **batch pipeline, not a chatbot** — a deliberate engineering choice (cheaper, more predictable),
wrapped in an on-demand agent entrypoint.

---

## 2. Final agreed design (locked 2026-06-11)

| Decision | Choice |
|--|--|
| **Platform** | VNG AgentBase **Custom Agent** — `greennode-agentbase` SDK, `@app.entrypoint`, `POST /invocations`, port 8080 |
| **LLM** | Single model **`google/gemma-4-31b-it`** via OpenAI-compatible **MaaS** (multimodal, 128K ctx) |
| **Trigger** | **On-demand** via `/invocations` (dispatch on `payload["action"]`); scheduling is external — no in-container scheduler |
| **ML (local)** | Keep **PhoBERT** (sentiment) + **MiniLM** (embeddings) + **ChromaDB**; **baked into the image**; runtime **4CPU/8GB** |
| **Connectors** | **Real** Jira/FB/Threads, with `dry_run` mock fallback |
| **Classification** | **RAG-grounded** — retrieve taxonomy/known-issue examples to ground domain/segment choices |
| **Positioning** | Batch report pipeline **+ agentic Q&A** over indexed issues |

The pipeline *design* (10 stages) was already sound — the work was **re-targeting it onto AgentBase** and
adding the two upgrades above, not redesigning it.

---

## 3. Tech stack (current & correct)

| Layer | Choice | Notes |
|--|--|--|
| LLM (all stages incl. vision) | `google/gemma-4-31b-it` via MaaS | OpenAI-compatible; `LLM_PROVIDER=openai` + `LLM_BASE_URL` |
| Local dev / Colab LLM | Google Gemini (`google-genai`) | Free tier; `gemini-2.5-flash` for SMART (pro is blocked: limit 0) |
| Sentiment | `wonrax/phobert-base-vietnamese-sentiment` | Offline ML; LLM tiebreaker only when borderline |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` | Used for RAG, taxonomy, grouping, issues store |
| Vector DB | ChromaDB | 3 collections: `knowledge_base`, `taxonomy`, `issues` |
| Runtime | `greennode-agentbase` Custom Agent | Docker, 4CPU/8GB, models + index baked in |
| Crawling (Bronze) | Offline crawlers → `data/raw/<source>_<ts>.jsonl` | **Threads = Playwright** public keyword search (base64 images, MD5 dedup) |
| Connectors | read latest bronze → normalize | `connectors/*` map raw → `{id,source,text,images,timestamp}` |

LLM access details, deploy commands, and gotchas: [[Tools/AgentBase Platform Guide]].

---

## 4. Pipeline (10 stages)

```
Fetch → Preprocess → [Sentiment filter*] → [Image analysis*] → Extract issue
   → RAG-grounded Classify (domain+segment) → Group (embeddings)
   → KB solution lookup (RAG) → Report (LLM) → Guardrails → save + index for Q&A
                                                            (* social job only)
```

**Stage 0 (offline): crawl → Bronze.** Crawlers run outside the agent and write
`data/raw/<source>_<ts>.jsonl`. Threads uses a **Playwright** public-keyword-search crawler
(`crawlers/threads_crawler.py`, base64 images + MD5 dedup). The **Fetch** stage above reads the latest
bronze file (`connectors/*`) — `dry_run=True` uses `mock_data.py` instead.

Guiding rule: **pre-filter with cheap code first, use the LLM only on what survives.**
Stage-by-stage walkthrough: [[Projects/Pipeline Deep Dive]]. Code map: [[Projects/Code Walkthrough]].

---

## 5. Deployment shape

- **Entrypoint** `main.py`: `handle_payload(payload)` dispatches on `action`:
  - `{"action":"run","job":"jira|social|all","dry_run":false}` → runs the pipeline, writes a report, indexes issues.
  - `{"action":"query","question":"..."}` → RAG over the issues store → grounded answer.
- `@app.ping` → `HEALTHY`. Served on port 8080 at `/invocations`.
- **Docker**: Python 3.11-slim, CPU torch, **PhoBERT + MiniLM + KB/taxonomy index baked at build** (no runtime HF download). Deploy on `runtime-s2-general-4x8`.
- Local dev harness (FastAPI + scheduler) preserved in `local_api.py` — **not** shipped.

---

## 6. Repo map

| Path | Role |
|--|--|
| `clawathon-aicbc-agent/` | **Production code** — the real project |
| `simple-agent/` | AgentBase onboarding sample (already deployed) — reference for the SDK shape |
| `tokenization/`, `embedding/` | Learning sandboxes — **not** production |
| `vault/` | This Obsidian knowledge base |

---

## 7. Build status (accurate, 2026-06-11)

| Area | Status |
|--|--|
| Pipeline (preprocess, sentiment, extract, classify, group, image, report, guardrails) | ✅ built |
| Knowledge base (5 solution docs + taxonomy), ChromaDB index | ✅ built |
| **RAG-grounded classification** (taxonomy collection + domain metadata) | ✅ built & verified |
| **Agentic Q&A** (`issues_store.py` + query action) | ✅ built & verified (mock e2e) |
| Connectors: Facebook, Threads | ✅ built |
| Connector: **Jira** | ✅ built (was a stub) |
| LLM client → MaaS (`base_url`, single Gemma) | ✅ built |
| AgentBase entrypoint `main.py` + `local_api.py` | ✅ built |
| Dependencies + Dockerfile (baked models/index) + AgentBase config templates | ✅ built |
| Local e2e on mock data (via Google) | ✅ verified (5/5 classification correct, report + Q&A grounded) |
| **MaaS Gemma live test (text + vision)** | ⛔ blocked — needs a real MaaS key |
| **Deploy to AgentBase** | ⛔ blocked — needs MaaS key + `.greennode.json` |

---

## 8. Open blockers & risks

- **MaaS credentials** — the existing key is a Google AI-Studio key (401 on MaaS). Need a real MaaS API key via `/agentbase-llm` and `clawathon-aicbc-agent/.greennode.json` (copy `.greennode.json.example`). Until then, MaaS text/vision is unverified.
- **Gemma vision via MaaS** — confirm the endpoint accepts `image_url` content for Gemma 4. If not, image analysis degrades to text-only (pipeline still works).
- **Invocation timeout** — a full real-data job may be slow; keep demo batches small.
- **Issues store persistence** — local ChromaDB resets on redeploy; fine for a demo. Upgrade path: AgentBase Memory/KB.

---

## 9. Doc index

**Project**
- [[Projects/Hackathon]] — overview & phases
- [[Projects/Architecture]] — system diagrams & components
- [[Projects/Pipeline Deep Dive]] — every stage, traced
- [[Projects/Code Walkthrough]] — file-by-file
- [[Projects/Data Sources]] — connectors
- [[Projects/Image Processing]] — Gemma vision
- [[Projects/Report Format]] — output structure
- [[Projects/Implementation Plan]] — build order
- [[Projects/Architecture Review]] — gaps & decisions
- [[Projects/Project_Context]] — narrative context

**Platform & frameworks**
- [[Tools/AgentBase Platform Guide]] — deploy, MaaS, skills
- [[Frameworks/Anthropic SDK]], [[Frameworks/LangGraph]], [[Frameworks/CrewAI]]

**Concepts**
- [[Concepts/RAG - Retrieval-Augmented Generation]], [[Concepts/Embeddings]], [[Concepts/Sentiment Analysis]],
  [[Concepts/Guardrails]], [[Concepts/LLM as a Processing Step]], [[Concepts/Tokenization & Text Preprocessing]]

Navigation: [[🏠 Home]] · [[📍 Roadmap]]
