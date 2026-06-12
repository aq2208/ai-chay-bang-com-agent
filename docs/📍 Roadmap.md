# Learning Roadmap — AI Agents for Hackathon

#roadmap

> [!tip] Building the actual project? Start at **[[Projects/00 - Project Home]]** — the canonical
> design/status hub. This roadmap is the learning plan that fed into it.

---

## The Mental Model to Never Forget

> **An agent is just an LLM in a while-loop with access to functions.**

Everything else is just making that loop smarter and more reliable.

---

## Phase 1 — Core Concepts (Days 1–2)

These are non-negotiable. Learn these before anything else.

| Concept                     | Note                                     | Status |
| --------------------------- | ---------------------------------------- | ------ |
| What is an AI Agent         | [[Concepts/What is an AI Agent]]         | ✅      |
| LLM API Basics              | [[Concepts/LLM API Basics]]              | ✅      |
| Tool Use / Function Calling | [[Concepts/Tool Use & Function Calling]] | ✅      |
| Agent Loop (ReAct)          | [[Concepts/Agent Loop - ReAct Pattern]]  | ✅      |
| Prompt Engineering basics   | [[Concepts/Prompt Engineering]]          | ✅      |

---

## Phase 2 — Practical Skills (Days 2–3)

| Concept | Note | Status |
|---------|------|--------|
| Anthropic SDK | [[Frameworks/Anthropic SDK]] | ✅ |
| LangGraph | [[Frameworks/LangGraph]] | ⬜ |
| CrewAI | [[Frameworks/CrewAI]] | ⬜ |
| Web Search Tools | [[Tools/Web Search Tools]] | ✅ |
| Vector Databases | [[Tools/Vector Databases]] | ✅ |
| Memory Types | [[Concepts/Memory Types]] | ✅ |

---

## Phase 3 — Advanced (Days 3–4)

| Concept | Note | Status |
|---------|------|--------|
| RAG | [[Concepts/RAG - Retrieval-Augmented Generation]] | ✅ |
| Multi-Agent Architecture | [[Concepts/Multi-Agent Architecture]] | ✅ |

---

## Phase 4 — Ship (Day 4–5)

| Task | Status |
|------|--------|
| Pick framework for hackathon | ⬜ |
| Build agent skeleton | ⬜ |
| Add tools specific to topic | ⬜ |
| Wrap in Streamlit UI | ⬜ |
| Polish and demo | ⬜ |

---

## Daily Plan

| Day | Goal |
|-----|------|
| Day 1 | Call Claude/GPT API. Build a simple chatbot. |
| Day 2 | Add one tool (web search). Build the agent loop manually. |
| Day 3 | Add 2–3 more tools. Add memory/RAG if needed. |
| Day 4 | Wire up hackathon use case. Add Streamlit UI. |
| Day 5 | Polish, test edge cases, prep demo. |

---

## Key Resources

1. [Anthropic Tool Use Docs](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
2. [LangGraph Quickstart](https://langchain-ai.github.io/langgraph/tutorials/introduction/)
3. [CrewAI Docs](https://docs.crewai.com)
4. [Simon Willison's LLM blog](https://simonwillison.net)
