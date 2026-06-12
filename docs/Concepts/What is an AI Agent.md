# What is an AI Agent?

#concept #foundation

---

## One-Line Definition

> An AI Agent is an LLM that can **observe**, **reason**, **act**, and **loop** until it finishes a goal.

---

## The Difference: Chatbot vs Agent

| | Chatbot | Agent |
|--|---------|-------|
| Input | One message | A goal |
| Output | One reply | A completed task |
| Steps | 1 | Many (it decides how many) |
| Tools | None | Web search, code, APIs, files... |
| Memory | Optional | Yes, needed for long tasks |

---

## The Four Core Components

### 1. Brain (LLM)
The language model that reasons, decides what to do next, and produces final output. Examples: Claude, GPT-4, Gemini.

### 2. Tools
Functions the LLM can call to interact with the world. Examples:
- `search_web(query)` — find information
- `run_python(code)` — execute code
- `read_file(path)` — read a document
- `call_api(url, params)` — talk to external services

### 3. Memory
How the agent remembers things. See [[Concepts/Memory Types]].

### 4. The Loop
The engine that keeps running until the goal is complete. See [[Concepts/Agent Loop - ReAct Pattern]].

---

## How an Agent Works (Big Picture)

```
You give the agent a goal
        ↓
Agent thinks: "What do I need to do first?"
        ↓
Agent calls a tool (e.g. searches the web)
        ↓
Tool result comes back
        ↓
Agent thinks again: "What's next?"
        ↓
... repeats until ...
        ↓
Agent says: "I'm done. Here's your answer."
```

---

## Simple Code Example

```python
import anthropic

client = anthropic.Anthropic()

# Define a tool the agent can use
tools = [
    {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"]
        }
    }
]

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "What's the weather in Hanoi?"}]
)

# If LLM wants to call a tool:
if response.stop_reason == "tool_use":
    tool_call = response.content[0]
    print(f"Agent wants to call: {tool_call.name}")
    print(f"With args: {tool_call.input}")
```

---

## Related Notes

- [[Concepts/LLM API Basics]] — how to talk to the LLM
- [[Concepts/Tool Use & Function Calling]] — how tools work
- [[Concepts/Agent Loop - ReAct Pattern]] — the loop in detail
- [[Concepts/Memory Types]] — how agents remember things
