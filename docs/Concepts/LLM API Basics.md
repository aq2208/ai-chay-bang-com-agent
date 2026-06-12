# LLM API Basics

#concept #foundation

---

## What This Is

Before building an agent, you need to know how to talk to an LLM programmatically. This is just sending messages via HTTP and getting text back.

---

## The Messages Format

Every LLM API uses the same core structure: a list of messages with roles.

```python
messages = [
    {"role": "user",      "content": "Hello!"},
    {"role": "assistant", "content": "Hi there!"},
    {"role": "user",      "content": "What is 2+2?"},
]
```

- `user` — what you (or the agent loop) sends
- `assistant` — what the LLM replied previously
- `system` — the LLM's instructions / personality (set once, not in the list)

The full conversation history is sent **every time**. The LLM has no memory between calls — you pass it all the history yourself.

---

## Anthropic (Claude) API

### Install
```bash
pip install anthropic
```

### Basic Call
```python
import anthropic

client = anthropic.Anthropic(api_key="your-key-here")
# or set env var: ANTHROPIC_API_KEY

response = client.messages.create(
    model="claude-sonnet-4-6",          # which model
    max_tokens=1024,                     # max reply length
    system="You are a helpful assistant.",
    messages=[
        {"role": "user", "content": "Explain recursion simply."}
    ]
)

print(response.content[0].text)         # the reply text
```

### Key Parameters

| Parameter     | What it does                                |
| ------------- | ------------------------------------------- |
| `model`       | Which Claude model to use                   |
| `max_tokens`  | Max length of the response                  |
| `system`      | System prompt (agent's instructions)        |
| `messages`    | The conversation history                    |
| `temperature` | 0 = deterministic, 1 = creative (default 1) |
| `tools`       | List of tools the model can call            |

### Current Claude Models (as of 2026)

| Model ID | Speed | Intelligence | Use for |
|----------|-------|-------------|---------|
| `claude-opus-4-8` | Slow | Highest | Complex reasoning |
| `claude-sonnet-4-6` | Fast | High | Most tasks ✅ |
| `claude-haiku-4-5-20251001` | Fastest | Good | Simple tasks |

---

## Conversation History Pattern

This is the pattern you'll use in every agent:

```python
history = []

def chat(user_message):
    history.append({"role": "user", "content": user_message})

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=history
    )

    reply = response.content[0].text
    history.append({"role": "assistant", "content": reply})
    return reply

# Multi-turn conversation
print(chat("My name is Quan."))
print(chat("What's my name?"))  # Claude will remember from history
```

---

## Stop Reasons

The `response.stop_reason` tells you why the LLM stopped:

| Stop Reason | Meaning |
|-------------|---------|
| `"end_turn"` | Normal finish — reply is complete |
| `"tool_use"` | LLM wants to call a tool (agent loop continues) |
| `"max_tokens"` | Hit the token limit — reply was cut off |

In an agent loop, `tool_use` means you need to run the tool and loop back.

---

## Tokens — What They Are

- LLMs don't read words, they read **tokens** (roughly 0.75 words each)
- "Hello world" ≈ 2 tokens
- Every API call costs tokens: input (your messages) + output (the reply)
- `max_tokens` caps the output length, not the input

---

## Related Notes

- [[Concepts/What is an AI Agent]] — why you need to call the LLM
- [[Concepts/Tool Use & Function Calling]] — next step after basic API calls
- [[Frameworks/Anthropic SDK]] — deeper SDK details
