# Anthropic SDK

#framework #tool

> [!note] Learning reference only. **The hackathon project does NOT use the Anthropic SDK.** It runs on
> **VNG AgentBase** with the **OpenAI-compatible MaaS** client (`google/gemma-4-31b-it`). The project's
> `llm_client` is provider-pluggable (openai/MaaS for prod, Google Gemini for dev), so the principles here
> still apply — just via a different SDK. Canonical design: **[[Projects/00 - Project Home]]**.

---

## Why Start Here

Before using any framework, learn the raw SDK. It teaches you what's actually happening under the hood. Frameworks just wrap this.

---

## Install & Setup

```bash
pip install anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
```

```python
import anthropic
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
```

---

## Core API Call

```python
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    system="You are a helpful assistant.",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.content[0].text)
print(response.stop_reason)          # "end_turn" or "tool_use"
print(response.usage.input_tokens)   # how many tokens you sent
print(response.usage.output_tokens)  # how many tokens in reply
```

---

## Response Object Structure

```python
response.id                    # unique message ID
response.model                 # model used
response.stop_reason           # "end_turn" | "tool_use" | "max_tokens"
response.usage.input_tokens    # tokens in
response.usage.output_tokens   # tokens out

response.content               # list of content blocks
# Each block is either:
#   TextBlock  → block.text (the reply text)
#   ToolUseBlock → block.name, block.input, block.id
```

```python
# How to extract text safely
for block in response.content:
    if hasattr(block, "text"):
        print(block.text)
    elif block.type == "tool_use":
        print(f"Tool: {block.name}, Args: {block.input}")
```

---

## Streaming (for UI responsiveness)

Stream tokens as they're generated instead of waiting for the full response:

```python
with client.messages.stream(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Write a poem"}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

---

## Full Agent Example

Complete working agent with tool use:

```python
import anthropic
import subprocess

client = anthropic.Anthropic()

tools = [
    {
        "name": "run_python",
        "description": "Execute Python code and return the output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"}
            },
            "required": ["code"]
        }
    }
]

def run_python(code: str) -> str:
    result = subprocess.run(["python", "-c", code],
                            capture_output=True, text=True, timeout=10)
    return result.stdout or result.stderr or "No output"

def run_agent(goal: str) -> str:
    messages = [{"role": "user", "content": goal}]

    for _ in range(20):  # max 20 iterations
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=tools,
            messages=messages
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text

        elif response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    if block.name == "run_python":
                        result = run_python(block.input["code"])
                    else:
                        result = f"Unknown tool: {block.name}"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            messages.append({"role": "user", "content": tool_results})

    return "Max iterations reached"

print(run_agent("What is 2^32? Use Python to calculate it."))
```

---

## Models Quick Reference

| Model | ID | Speed | Best for |
|-------|----|-------|---------|
| Opus | `claude-opus-4-8` | Slow | Hard reasoning tasks |
| Sonnet | `claude-sonnet-4-6` | Fast | Most agent tasks ✅ |
| Haiku | `claude-haiku-4-5-20251001` | Fastest | Simple, high-volume tasks |

---

## Related Notes

- [[Concepts/LLM API Basics]] — API fundamentals
- [[Concepts/Tool Use & Function Calling]] — how tools work in the SDK
- [[Concepts/Agent Loop - ReAct Pattern]] — the loop this SDK powers
