# CrewAI

#framework

---

## What It Is

CrewAI is the simplest framework for multi-agent teams. You define agents with roles, assign them tasks, and CrewAI handles the orchestration.

Best for hackathons — high-level, minimal boilerplate.

---

## Install

```bash
pip install crewai crewai-tools
```

---

## Core Concepts

| Concept | What it is |
|---------|-----------|
| **Agent** | An LLM with a role, goal, backstory, and tools |
| **Task** | A specific job assigned to an agent |
| **Crew** | A team of agents + tasks, with an execution strategy |
| **Tool** | A function agents can call (web search, code, etc.) |

---

## Minimal Example

```python
from crewai import Agent, Task, Crew
from crewai_tools import SerperDevTool

search_tool = SerperDevTool()  # Google search

# Define agents
researcher = Agent(
    role="Research Analyst",
    goal="Find accurate information about {topic}",
    backstory="""You are an expert researcher who finds reliable, 
    current information from the web.""",
    tools=[search_tool],
    verbose=True
)

writer = Agent(
    role="Content Writer",
    goal="Write clear, engaging content based on research",
    backstory="""You are a skilled writer who turns research 
    findings into readable reports.""",
    verbose=True
)

# Define tasks
research_task = Task(
    description="Research the following topic thoroughly: {topic}. Find key facts, recent developments, and reliable sources.",
    expected_output="A detailed summary with bullet points and sources.",
    agent=researcher
)

writing_task = Task(
    description="Using the research provided, write a 500-word report on {topic}.",
    expected_output="A polished, well-structured report ready to publish.",
    agent=writer,
    context=[research_task]  # this task uses research_task's output
)

# Assemble crew
crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, writing_task],
    verbose=True
)

# Run
result = crew.kickoff(inputs={"topic": "AI agents in 2025"})
print(result)
```

---

## Execution Strategies

```python
from crewai import Process

# Sequential (default) — tasks run one after another
crew = Crew(..., process=Process.sequential)

# Hierarchical — a manager LLM assigns tasks dynamically
crew = Crew(..., process=Process.hierarchical, manager_llm="claude-sonnet-4-6")
```

---

## Using Claude as the LLM

```python
from crewai import Agent, LLM

claude = LLM(model="anthropic/claude-sonnet-4-6")

agent = Agent(
    role="Analyst",
    goal="Analyze data",
    backstory="Expert data analyst",
    llm=claude
)
```

---

## Built-in Tools

```python
from crewai_tools import (
    SerperDevTool,        # Google search
    WebsiteSearchTool,    # Search a specific website
    FileReadTool,         # Read files
    CodeInterpreterTool,  # Run Python code
    PDFSearchTool,        # Search inside PDFs
)
```

---

## CrewAI vs LangGraph

| | CrewAI | LangGraph |
|--|--------|-----------|
| Learning curve | Low | Medium |
| Control | Less | More |
| Best for | Multi-agent teams with roles | Complex flows with conditions |
| Hackathon speed | Fast to prototype | Takes more setup |
| Human-in-the-loop | Limited | Built-in |

**Hackathon recommendation:** Start with CrewAI. Switch to LangGraph only if you need conditional branching or complex state management.

---

## Related Notes

- [[Concepts/Multi-Agent Architecture]] — the patterns CrewAI implements
- [[Frameworks/LangGraph]] — the alternative for more control
- [[Frameworks/Anthropic SDK]] — what CrewAI uses under the hood
