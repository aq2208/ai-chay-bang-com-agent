# Memory Types

#concept #core

---

## Why Agents Need Memory

LLMs are stateless — each API call is independent. The "memory" you see is just the conversation history you pass in manually. For longer tasks, agents need structured ways to remember things.

---

## The Four Types of Memory

### 1. Short-Term Memory (In-Context)
**What:** The conversation history array you pass to every API call.  
**Limit:** Context window size (Claude: up to 200K tokens ≈ ~150,000 words)  
**Cost:** Every token in history costs money each call  

```python
# This IS the short-term memory
messages = [
    {"role": "user",      "content": "My name is Quan."},
    {"role": "assistant", "content": "Nice to meet you, Quan!"},
    {"role": "user",      "content": "What's my name?"},
    # LLM sees all of the above and knows the answer
]
```

**When to use:** Tasks that fit in a single conversation. Default for most agents.

---

### 2. External Memory (Database / Files)
**What:** Storing information outside the LLM (database, files, Redis).  
**Limit:** Unlimited  
**Use:** Long-running agents that need to remember things across sessions  

```python
import json, os

def save_memory(key: str, value: str):
    memory = load_memory()
    memory[key] = value
    with open("agent_memory.json", "w") as f:
        json.dump(memory, f)

def load_memory() -> dict:
    if os.path.exists("agent_memory.json"):
        with open("agent_memory.json") as f:
            return json.load(f)
    return {}

# Agent can call save_memory("user_name", "Quan") as a tool
# And load_memory() at the start of each session
```

**When to use:** When the agent needs to persist info between separate runs.

---

### 3. Semantic Memory (Vector Database)
**What:** Storing text as embeddings so you can search by *meaning*, not keywords.  
**Use:** RAG (Retrieval-Augmented Generation) — searching large document collections  

See [[Concepts/RAG - Retrieval-Augmented Generation]] for full details.

```python
# Store: "The capital of Vietnam is Hanoi" → [0.23, -0.41, 0.88, ...]
# Query: "Where is Vietnam's government?" → finds the stored text by meaning
```

**When to use:** When you have a knowledge base (docs, PDFs, articles) and need to find relevant information.

---

### 4. Episodic Memory (Summaries)
**What:** Summarizing past conversations so they fit back into the context window.  
**Use:** Very long-running agents or chatbots with long history  

```python
# When conversation gets long:
summary_prompt = f"Summarize this conversation in 3 bullet points:\n{old_messages}"
summary = llm.call(summary_prompt)

# Replace old messages with summary
messages = [
    {"role": "user", "content": f"Previous conversation summary:\n{summary}"},
    # ... continue with recent messages
]
```

**When to use:** When conversation history overflows the context window.

---

## Memory Decision Guide

```
Do I need to remember across separate sessions?
├── Yes → External Memory (database/files)
└── No → Does my document collection fit in one prompt?
           ├── Yes → Short-term Memory (just pass it in)
           └── No → Semantic Memory (RAG with vector DB)
```

---

## Practical Recommendation for Hackathon

Start with **short-term memory only** (just the messages list). Add external or semantic memory only if your use case requires it.

- Simple chatbot agent → short-term only
- Agent that reads many documents → semantic (RAG)
- Agent that runs across multiple days → external (files/DB)

---

## Related Notes

- [[Concepts/RAG - Retrieval-Augmented Generation]] — semantic memory in detail
- [[Tools/Vector Databases]] — tools for semantic memory
- [[Concepts/Agent Loop - ReAct Pattern]] — where memory plugs into the loop
