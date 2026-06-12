# Hackathon Project — Data Analytic Agent

#project

> [!info] Canonical design: **[[Projects/00 - Project Home]]**. Updated 2026-06-11:
> **LLM = `google/gemma-4-31b-it` via AgentBase MaaS** (one model — any Claude/Gemini/GPT mentions
> below are historical). **Deploy = AgentBase Custom Agent** (`/invocations`), not FastAPI/Streamlit
> in production. Now also includes **RAG-grounded classification** and an **agentic Q&A** endpoint.

---

## Topic

**Data Analytics Agent** that ingests user feedback from multiple sources (Jira + social media), analyzes and filters it, classifies by domain, and generates structured issue reports with suggested solutions for Product Owners.

---

## What It Does (End to End)

Two independent jobs, each schedulable and manually triggerable:

```
JOB 1 — Jira                        JOB 2 — Social Media
─────────────────────                ──────────────────────────────────
[Jira API]                           [Facebook] + [Threads]  (parallel)
     ↓                                       ↓
All tickets pass through             Keyword search → sentiment filter
     ↓                                       ↓
Extract + classify domain/segment    Image analysis (Claude Vision)
     ↓                                       ↓
RAG → suggested solutions            Extract + classify domain/segment
     ↓                                       ↓
jira_report.md                       RAG → suggested solutions
                                             ↓
                                     social_report.md
```

**Job 1 steps:** Ingest → Extract → Classify → RAG → Report  
**Job 2 steps:** Ingest → Keyword filter → Sentiment filter → Image analysis → Extract → Classify → RAG → Report

---

## Output: Issue Report (v1)

One report per domain, containing:

```markdown
# Domain: Payment

## Issue #1 — Top-up failure with Visa card
**Source:** Facebook post (3 mentions) + Jira TICKET-1234
**Description:** Users report Visa card top-up failing at checkout with error "Payment declined".
**Suggested Solution:** Check payment gateway timeout config. Known fix: increase retry limit to 3.

## Issue #2 — ...
```

---

## Architecture

See [[Projects/Architecture]] for the full diagram and component breakdown.

---

## Tech Stack

| Component | Choice | Why |
|-----------|--------|-----|
| LLM (all stages incl. vision) | `google/gemma-4-31b-it` via AgentBase MaaS | The only platform model; multimodal, 128K ctx, OpenAI-compatible |
| Local/Colab dev LLM | Google Gemini (`google-genai`) | Free tier for stage-by-stage testing |
| Framework | `greennode-agentbase` SDK + pipeline | Custom Agent on AgentBase; pluggable `llm_client` |
| Vector DB | ChromaDB | Local, free; collections: `knowledge_base`, `taxonomy`, `issues` |
| Knowledge Base | RAG over team docs (+ taxonomy) | [[Concepts/RAG - Retrieval-Augmented Generation]] — also grounds classification |
| Jira | Jira REST API (`jira` Python lib) | Official API |
| Social Media | Facebook Graph API + Threads API | See [[Projects/Data Sources]] |
| Trigger | On-demand `POST /invocations` | `{"action":"run"|"query", ...}`; scheduling external |
| Report output | Markdown (returned + saved) | Easy to read, easy to generate |

---

## Phases

### Phase 1 — MVP (Hackathon Demo)

**Job 1 (Jira):**
- [ ] Mock Jira data (5–10 tickets)
- [ ] Domain + segment classifier
- [ ] RAG knowledge base (5 solution docs)
- [ ] Jira report generator → `jira_report.md`
- [ ] Manual trigger: `python main.py --job jira`

**Job 2 (Social):**
- [ ] Mock social data (5–10 posts, 2–3 with images)
- [ ] Sentiment filter
- [ ] Image analysis with Claude Vision + sample images
- [ ] Social report generator → `social_report.md`
- [ ] Manual trigger: `python main.py --job social`

**Shared:**
- [ ] FastAPI with `/run/jira`, `/run/social`, `/run/all`
- [ ] Table-format reports (see [[Projects/Report Format]])

### Phase 2 — If Time Allows
- [ ] Real Jira API
- [ ] Facebook keyword search + comments
- [ ] Threads keyword search
- [ ] APScheduler (8am daily, both jobs)
- [ ] HTML/PDF report export

---

## Team

> Fill in members and ownership.

| Member | Owns |
|--------|------|
| | Data ingestion |
| | LLM pipeline |
| | Knowledge base / RAG |
| | Report generation + UI |

---

## Key Decisions

- **Gemma 4 for images** — `google/gemma-4-31b-it` is multimodal. Pass the post image + sample images via OpenAI-style `image_url` content. No separate vision model needed. (Confirm the MaaS endpoint accepts image content; if not, image analysis degrades to text-only.)
- **Pipeline, not conversational** — this is a batch processing job, not a chatbot. The agent loop is replaced by a deterministic sequence of LLM calls, wrapped in an on-demand `/invocations` entrypoint.
- **RAG for solutions AND classification** — team docs are indexed for solution lookup; a taxonomy collection grounds domain/segment classification (retrieve similar known issues → classify more precisely).
- **Agentic Q&A** — each run indexes its issues into an `issues` collection; the `query` action answers PO questions via RAG over those issues.
- **`dry_run` mock data** — real social APIs need app approval; mocks let the pipeline be built/demoed, with real connectors wired in.

---

## Related Notes

- [[Projects/Architecture]] — full system diagram
- [[Projects/Data Sources]] — Jira + social media API details
- [[Concepts/RAG - Retrieval-Augmented Generation]] — knowledge base
- [[Concepts/Multi-Agent Architecture]] — pipeline agent pattern
- [[Projects/Image Processing]] — Claude Vision for social media images
