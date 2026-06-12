# Prompt Engineering

#concept #foundation

---

## What It Is

Prompt engineering is writing instructions for the LLM that make it behave exactly how you want. For agents, this mostly means the **system prompt**.

---

## System Prompt = Agent's Brain Configuration

The system prompt is read by the LLM before every message. It defines:
- Who the agent is
- What it can do
- How it should behave
- Any constraints

```python
system_prompt = """
You are a research assistant agent. Your job is to answer questions 
about technology by searching the web and synthesizing accurate, 
concise responses.

You have access to these tools:
- search_web: search the internet for current information
- read_url: read the content of a webpage

Guidelines:
- Always search before answering factual questions — don't rely on your training data
- Cite your sources in the final answer
- If you can't find reliable information, say so
- Keep answers under 300 words unless the user asks for more detail
"""
```

---

## The Core Techniques

### 1. Be Specific, Not Vague

Bad: "Answer helpfully."  
Good: "Answer in 3 bullet points. Start with the most important point."

### 2. Assign a Role

```
You are a senior Python developer reviewing code for security vulnerabilities.
```
This activates relevant knowledge and sets a clear perspective.

### 3. Chain-of-Thought

Tell the LLM to think before answering:
```
Before giving your final answer, think through the problem step by step.
Write your reasoning first, then your conclusion.
```

### 4. Constrain Output Format

```
Always respond in this format:
THOUGHT: [your reasoning]
ACTION: [tool to call or "FINAL ANSWER"]
```

### 5. Give Examples (Few-Shot)

```
Here are examples of how to respond:

User: What's 2+2?
Assistant: 4

User: What's the capital of France?
Assistant: Paris
```

---

## Agent-Specific Prompting

For agents, the system prompt should also explain:

```
You have access to the following tools. Use them when needed:

search_web(query) — search the internet
run_python(code) — execute Python code

When you have enough information to answer, give your final response directly.
Do not call tools if you already know the answer with high confidence.
```

### Tell It When to Stop
```
After gathering the information you need, synthesize it into a clear answer.
Do not keep searching if you have enough information.
```

### Handle Uncertainty
```
If you cannot find reliable information, say "I couldn't find reliable data on this"
rather than guessing.
```

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Too vague: "Be helpful" | Specific: "Answer in bullet points, cite sources" |
| No format constraint | Tell it exactly how to structure output |
| Not telling it when to stop | Add explicit "stop when you have enough info" |
| Not mentioning tools | List each tool and when to use it |
| Overloading the prompt | One clear role, 5–8 guidelines max |

---

## Temperature

The `temperature` parameter controls randomness:

| Temperature | Behavior | Use for |
|-------------|----------|---------|
| `0.0` | Deterministic, always same answer | Factual tasks, JSON output |
| `0.5` | Balanced | Most agent tasks |
| `1.0` | Creative, more varied | Brainstorming, writing |

For agents doing research or analysis: `temperature=0` or `0.2` for consistency.

---

## Related Notes

- [[Concepts/LLM API Basics]] — where the system prompt goes in the API call
- [[Concepts/Agent Loop - ReAct Pattern]] — prompting affects how the loop behaves
- [[Concepts/Tool Use & Function Calling]] — how to describe tools in prompts
