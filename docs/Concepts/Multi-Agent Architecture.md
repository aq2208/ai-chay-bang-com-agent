# Multi-Agent Architecture

#concept #advanced

---

## Why Multiple Agents?

One agent trying to do everything becomes confused and makes mistakes. Split the work across specialist agents — each focused on one job.

**Analogy:** A company has specialists (researcher, writer, reviewer) coordinated by a manager, not one person doing everything.

---

## Core Pattern: Orchestrator + Workers

```
User Goal
    ↓
Orchestrator Agent
(plans and delegates)
    ├──→ Research Agent → searches web, gathers facts
    ├──→ Analysis Agent → processes and reasons over data
    └──→ Writer Agent   → formats and produces final output
    ↓
Final Answer
```

---

## Implementation: Simple Orchestrator

```python
import anthropic

client = anthropic.Anthropic()

def research_agent(question: str) -> str:
    """Specialist: searches and gathers information."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system="You are a research specialist. Search for accurate, current information.",
        tools=[search_web_tool],
        messages=[{"role": "user", "content": f"Research this: {question}"}]
    )
    # (run agent loop, return final text)
    return run_agent_loop(response, [search_web_tool])

def writer_agent(research: str, goal: str) -> str:
    """Specialist: formats research into a clear output."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system="You are a professional writer. Turn research into clear, concise reports.",
        messages=[{
            "role": "user",
            "content": f"Goal: {goal}\n\nResearch findings:\n{research}\n\nWrite the final report."
        }]
    )
    return response.content[0].text

def orchestrator(user_goal: str) -> str:
    """Coordinator: breaks goal into tasks, delegates to specialists."""
    # Step 1: Research
    research = research_agent(user_goal)

    # Step 2: Write
    report = writer_agent(research, user_goal)

    return report

# Run
result = orchestrator("Summarize the latest trends in AI agents")
```

---

## Communication Patterns

### Sequential (Pipeline)
Each agent's output is the next agent's input.
```
Agent A → output → Agent B → output → Agent C → Final
```
Best for: multi-step workflows where order matters.

### Parallel
Multiple agents run at the same time, results merged.
```
Agent A ─┐
Agent B ─┼→ Merge → Final
Agent C ─┘
```
Best for: independent sub-tasks (e.g. research 3 topics simultaneously).

### Hierarchical
Orchestrator spawns sub-orchestrators, which spawn workers.
```
Orchestrator
├── Sub-Orchestrator A
│   ├── Worker 1
│   └── Worker 2
└── Sub-Orchestrator B
    └── Worker 3
```
Best for: very complex tasks with many sub-domains.

---

## Multi-Agent with CrewAI (Easiest for Hackathon)

```python
from crewai import Agent, Task, Crew

researcher = Agent(
    role="Research Specialist",
    goal="Find accurate, current information on the given topic",
    backstory="Expert at searching the web and evaluating sources",
    tools=[search_tool],
    llm="claude-sonnet-4-6"
)

writer = Agent(
    role="Technical Writer",
    goal="Turn research into clear, concise reports",
    backstory="Skilled at making complex information accessible",
    llm="claude-sonnet-4-6"
)

research_task = Task(
    description="Research: {topic}",
    agent=researcher,
    expected_output="A detailed summary of findings with sources"
)

writing_task = Task(
    description="Write a report based on the research",
    agent=writer,
    expected_output="A polished 500-word report",
    context=[research_task]  # uses researcher's output
)

crew = Crew(agents=[researcher, writer], tasks=[research_task, writing_task])
result = crew.kickoff(inputs={"topic": "AI agent trends 2025"})
```

---

## When to Use Multi-Agent

Use a single agent when:
- The task fits in one conversation
- One LLM can handle all the complexity
- You're prototyping (start simple!)

Use multi-agent when:
- Different steps need different expertise
- Tasks can run in parallel to save time
- One agent keeps losing context over long tasks
- You want checks/reviews built in (one agent reviews another's work)

---

## Related Notes

- [[Concepts/Agent Loop - ReAct Pattern]] — each agent has its own loop
- [[Frameworks/CrewAI]] — simplest multi-agent framework
- [[Frameworks/LangGraph]] — best for complex agent workflows
- [[Projects/Hackathon]] — which pattern fits your topic
