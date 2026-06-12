# What is an Agent Framework?

#concept #framework

---

## One-Line Answer

An agent framework is a **library that handles the repetitive plumbing of building agents** so you can focus on what your agent actually does.

---

## The Problem It Solves

When you build an agent from scratch, you have to write the same boilerplate every time:

```python
# Every agent needs this exact same loop...
while True:
    response = llm.call(messages)
    messages.append(response)

    if response.stop_reason == "end_turn":
        return extract_text(response)

    elif response.stop_reason == "tool_use":
        results = []
        for block in response.content:
            if block.type == "tool_use":
                result = run_tool(block.name, block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
        messages.append({"role": "user", "content": results})
```

This loop is always the same. A framework writes it once so you don't have to.

---

## What a Framework Gives You

| Feature | Without Framework | With Framework |
|---------|-----------------|---------------|
| Agent loop | Write it yourself | Built-in |
| Tool registration | Manual JSON schemas | Decorators or classes |
| State management | Manage messages list | Handled automatically |
| Multi-agent orchestration | Complex custom code | A few config lines |
| Memory/persistence | Build from scratch | Plugins available |
| Error handling & retries | Write it yourself | Built-in |
| Streaming | Manual implementation | Built-in |

---

## Analogy: Framework vs No Framework

**No framework** = building a house by cutting trees, firing bricks, and mixing cement yourself.

**With framework** = buying pre-cut lumber, pre-made bricks, and pre-mixed cement. You still design the house — you just don't start from raw materials.

---

## Raw SDK vs Framework: Same Result, Different Code

### Goal: Agent that searches the web

**Raw Anthropic SDK (~60 lines):**
```python
def run_agent(goal):
    messages = [{"role": "user", "content": goal}]
    for _ in range(20):
        response = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=4096,
            tools=tools, messages=messages
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "end_turn":
            return extract_text(response)
        elif response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            messages.append({"role": "user", "content": tool_results})
```

**With LangGraph (~15 lines):**
```python
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(
    model="claude-sonnet-4-6",
    tools=[search_web]
)
result = agent.invoke({"messages": [("user", goal)]})
```

**With CrewAI (~10 lines):**
```python
researcher = Agent(role="Researcher", goal="Find info", tools=[search_web])
task = Task(description=goal, agent=researcher)
crew = Crew(agents=[researcher], tasks=[task])
result = crew.kickoff()
```

All three do the same thing. The framework just removes boilerplate.

---

## When to Use Raw SDK vs Framework

| Situation | Use |
|-----------|-----|
| Learning how agents work | **Raw SDK** — see exactly what's happening |
| Simple single agent | **Raw SDK** — no overhead needed |
| Multi-agent team | **CrewAI** — handles orchestration |
| Complex conditional flows | **LangGraph** — full graph control |
| Production system | **LangGraph** — best observability and control |
| Hackathon prototype | **CrewAI** or **Raw SDK** — fastest to ship |

---

## The Tradeoff

**More framework = less control, faster build**  
**Less framework = more control, slower build**

Start with raw SDK to understand what's happening. Once you understand the loop, move to a framework to go faster.

---

## Available Frameworks (Landscape)

| Framework | Made by | Style | Best for |
|-----------|---------|-------|---------|
| **LangGraph** | LangChain | Graph-based state machine | Complex flows, production |
| **CrewAI** | CrewAI | Role-based agents | Multi-agent teams |
| **AutoGen** | Microsoft | Conversation-based | Agent-to-agent chat |
| **Pydantic AI** | Pydantic team | Type-safe, minimal | Clean Python codebases |
| **Agno** | Agno team | Lightweight | Fast prototyping |
| **Raw SDK** | Anthropic/OpenAI | Manual | Learning, simple agents |

---

## Related Notes

- [[Frameworks/Anthropic SDK]] — the raw SDK (no framework)
- [[Frameworks/LangGraph]] — best for complex flows
- [[Frameworks/CrewAI]] — best for multi-agent teams
- [[Concepts/Agent Loop - ReAct Pattern]] — what frameworks automate
