# Tool Use & Function Calling

#concept #core

---

## What Tools Are

Tools give the LLM "hands" — ways to interact with the world beyond just generating text.

Without tools → LLM can only talk  
With tools → LLM can search, calculate, read files, call APIs, run code

---

## How It Works (the contract)

1. **You define** what tools exist (as JSON schemas)
2. **LLM decides** when and how to call them
3. **You run** the actual code when the LLM requests it
4. **You return** the result back to the LLM
5. **LLM continues** reasoning with the new information

The LLM never runs code itself. It just says "please call this tool with these arguments."

---

## Defining a Tool

A tool definition has three parts: name, description, and input schema.

```python
tools = [
    {
        "name": "search_web",
        "description": "Search the web for current information. Use this when you need facts you don't know.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "run_python",
        "description": "Execute Python code and return the output. Use for calculations or data processing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to run"
                }
            },
            "required": ["code"]
        }
    }
]
```

> The `description` is critical — the LLM reads it to decide when to use the tool. Write it clearly.

---

## Handling a Tool Call

```python
import anthropic
import subprocess

client = anthropic.Anthropic()

def run_python(code: str) -> str:
    result = subprocess.run(
        ["python", "-c", code],
        capture_output=True, text=True, timeout=10
    )
    return result.stdout or result.stderr

# Send message with tools
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "What is 1234 * 5678?"}]
)

# Check if LLM wants to call a tool
if response.stop_reason == "tool_use":
    for block in response.content:
        if block.type == "tool_use":
            tool_name = block.name        # e.g. "run_python"
            tool_args = block.input       # e.g. {"code": "print(1234*5678)"}
            tool_use_id = block.id        # needed to send result back

            # Run the tool
            if tool_name == "run_python":
                result = run_python(tool_args["code"])

            # Send result back to LLM
            # (see Agent Loop for full pattern)
```

---

## Sending the Tool Result Back

After running the tool, you add it to the conversation and call the LLM again:

```python
# Build the next messages list
messages = [
    {"role": "user", "content": "What is 1234 * 5678?"},
    {"role": "assistant", "content": response.content},  # LLM's tool_use request
    {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result  # the output from running the tool
            }
        ]
    }
]

# Call LLM again with result — it will now give a final answer
final_response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    tools=tools,
    messages=messages
)
```

---

## Tool Design Tips

- **Good descriptions beat good schemas** — the LLM uses descriptions to decide what to call
- **One tool, one job** — don't make a tool that does three things
- **Return useful error messages** — if a tool fails, return a string saying what went wrong, so the LLM can adjust
- **Be specific in descriptions** — "Use this when you need real-time data" is better than "Gets data"

---

## Common Tools to Build

| Tool | What it does | Library |
|------|-------------|---------|
| `search_web` | Search the internet | Tavily API, SerpAPI |
| `run_python` | Execute code | `subprocess` |
| `read_file` | Read a file | built-in `open()` |
| `call_api` | Call any HTTP endpoint | `requests` |
| `query_database` | Run SQL | `sqlite3`, `psycopg2` |
| `vector_search` | Semantic search over docs | ChromaDB, Pinecone |

---

## Related Notes

- [[Concepts/Agent Loop - ReAct Pattern]] — how tool calls fit into the full loop
- [[Concepts/What is an AI Agent]] — why tools matter
- [[Tools/Web Search Tools]] — specific web search setup
