# Agent Loop — ReAct Pattern

#concept #core

---

## What ReAct Means

**Re**ason + **Act** — the agent alternates between thinking and doing.

> Published in the paper "ReAct: Synergizing Reasoning and Acting in Language Models" (2022)

---

## The Loop in Plain English

```
Goal received
    ↓
THINK: What should I do first?
    ↓
ACT: Call a tool
    ↓
OBSERVE: Get the tool result
    ↓
THINK: What did I learn? What's next?
    ↓
ACT: Call another tool (or return final answer)
    ↓
... repeat until done ...
```

---

## Minimal Agent Loop in Python

This is the most important code pattern to understand. Everything else builds on this.

```python
import anthropic

client = anthropic.Anthropic()

def run_tool(name: str, args: dict) -> str:
    """Execute whatever tool the LLM requested."""
    if name == "search_web":
        return search_web(args["query"])
    elif name == "run_python":
        return run_python(args["code"])
    else:
        return f"Unknown tool: {name}"

def run_agent(goal: str, tools: list) -> str:
    """The agent loop. Runs until the LLM gives a final answer."""
    messages = [{"role": "user", "content": goal}]

    while True:
        # Ask the LLM what to do
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=tools,
            messages=messages
        )

        # Add LLM's response to history
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # LLM is done — extract and return the text
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text

        elif response.stop_reason == "tool_use":
            # LLM wants to call one or more tools
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    result = run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            # Feed all results back into the conversation
            messages.append({"role": "user", "content": tool_results})

        else:
            # max_tokens or other stop — return what we have
            break

    return "Agent stopped unexpectedly."

# Run it
answer = run_agent("What's the capital of Vietnam and what's its population?", tools)
print(answer)
```

---

## What Happens Step by Step

```
messages = [{"role": "user", "content": "What's Vietnam's capital population?"}]

--- Iteration 1 ---
LLM response: "I'll search for this."  stop_reason = "tool_use"
                tool_use: search_web("Vietnam capital population")

We run: search_web("Vietnam capital population")
Result: "Hanoi, population ~8 million"

messages now has: user goal + assistant tool_use + user tool_result

--- Iteration 2 ---
LLM response: "Hanoi is the capital with ~8 million people."  stop_reason = "end_turn"

Loop exits. Return the text.
```

---

## Parallel Tool Calls

The LLM can request multiple tools in one response. The loop handles all of them before continuing:

```python
# LLM might return two tool_use blocks at once:
# 1. search_web("Vietnam capital")
# 2. search_web("Vietnam area size")
# Run both, return both results together — this is more efficient
```

---

## Loop Safety

Always add a max iterations guard to prevent infinite loops:

```python
MAX_ITERATIONS = 20

for iteration in range(MAX_ITERATIONS):
    response = client.messages.create(...)
    
    if response.stop_reason == "end_turn":
        return extract_text(response)
    elif response.stop_reason == "tool_use":
        # handle tools
        pass

return "Max iterations reached."
```

---

## Related Notes

- [[Concepts/Tool Use & Function Calling]] — what happens when `stop_reason == "tool_use"`
- [[Concepts/What is an AI Agent]] — the big picture
- [[Frameworks/LangGraph]] — a framework that manages this loop for you
