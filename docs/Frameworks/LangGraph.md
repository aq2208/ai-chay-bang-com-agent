# LangGraph

#framework

---

## What It Is

LangGraph is a framework for building **stateful agents** as graphs. Instead of a simple while-loop, you define nodes (steps) and edges (transitions) — giving you full control over the agent's flow.

```
START → research_node → analysis_node → write_node → END
              ↑                                ↓
              └──── (if needs more info) ──────┘
```

---

## When to Use LangGraph

✅ Use LangGraph when:
- Your agent has conditional branching ("if research fails, try another approach")
- You need human-in-the-loop checkpoints
- Multiple agents need to hand off work
- You want persistent state between runs

❌ Use raw SDK when:
- Simple single-agent loop is enough
- Prototyping quickly
- You're still learning

---

## Install

```bash
pip install langgraph langchain-anthropic
```

---

## Core Concepts

### State
A typed dictionary that flows through the graph. Every node reads from and writes to it.

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # conversation history
    research: str                             # custom field
    done: bool
```

### Nodes
Python functions that take state and return updated state.

```python
def research_node(state: AgentState) -> AgentState:
    # Do research
    result = search_web(state["messages"][-1].content)
    return {"research": result}

def llm_node(state: AgentState) -> AgentState:
    response = client.messages.create(...)
    return {"messages": [response]}
```

### Edges
Control which node runs next.

```python
# Conditional edge
def should_continue(state: AgentState) -> str:
    if state["done"]:
        return "end"
    return "research"

graph.add_conditional_edges("llm_node", should_continue, {
    "end": END,
    "research": "research_node"
})
```

---

## Minimal LangGraph Agent

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]

# Tools (LangChain format)
from langchain_community.tools.tavily_search import TavilySearchResults
tools = [TavilySearchResults(max_results=3)]

# LLM bound to tools
llm = ChatAnthropic(model="claude-sonnet-4-6").bind_tools(tools)

def call_llm(state: State):
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

# Build graph
graph = StateGraph(State)
graph.add_node("llm", call_llm)
graph.add_node("tools", ToolNode(tools))

graph.set_entry_point("llm")
graph.add_conditional_edges("llm", tools_condition)  # goes to "tools" or END
graph.add_edge("tools", "llm")  # after tools, always go back to LLM

app = graph.compile()

# Run
result = app.invoke({"messages": [HumanMessage("What's happening in AI today?")]})
print(result["messages"][-1].content)
```

---

## Human-in-the-Loop

LangGraph lets you pause and wait for human approval:

```python
from langgraph.checkpoint.memory import MemorySaver

# Add checkpointer for persistence
app = graph.compile(checkpointer=MemorySaver(), interrupt_before=["tools"])

# Run until it hits a tool call
thread = {"configurable": {"thread_id": "1"}}
result = app.invoke(input, thread)

# Review the pending tool call
pending = app.get_state(thread).next  # shows what's about to happen

# Approve and continue
app.invoke(None, thread)  # resume from where it paused
```

---

## Related Notes

- [[Concepts/Agent Loop - ReAct Pattern]] — LangGraph automates this loop
- [[Concepts/Multi-Agent Architecture]] — LangGraph handles multi-agent flows well
- [[Frameworks/Anthropic SDK]] — the underlying SDK LangGraph uses
