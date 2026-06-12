# Web Search Tools

#tool

---

## Why Agents Need Web Search

LLMs have a training cutoff. For current events, real-time data, or anything that changes, the agent needs to search the web.

---

## Option 1: Tavily (Recommended for Agents)

Tavily is built specifically for LLM agents — returns clean, summarized results rather than raw HTML.

```bash
pip install tavily-python
export TAVILY_API_KEY="tvly-..."  # free tier: 1000 searches/month
```

```python
from tavily import TavilyClient

tavily = TavilyClient(api_key="tvly-...")

result = tavily.search(
    query="latest AI agent frameworks 2025",
    max_results=5,
    search_depth="basic"   # or "advanced" for deeper results
)

for r in result["results"]:
    print(r["title"])
    print(r["url"])
    print(r["content"])   # clean extracted text, not raw HTML
    print("---")
```

### As an Agent Tool

```python
def search_web(query: str) -> str:
    results = tavily.search(query=query, max_results=3)
    output = []
    for r in results["results"]:
        output.append(f"Source: {r['url']}\n{r['content']}")
    return "\n\n---\n\n".join(output)

# Tool definition
search_tool = {
    "name": "search_web",
    "description": "Search the internet for current information. Use for recent events, facts, or anything outside your training data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"}
        },
        "required": ["query"]
    }
}
```

---

## Option 2: SerpAPI (Google Results)

Returns actual Google search results. More powerful, costs more.

```bash
pip install google-search-results
```

```python
from serpapi import GoogleSearch

params = {
    "q": "AI agent tutorials",
    "api_key": "your-serpapi-key"
}

search = GoogleSearch(params)
results = search.get_dict()["organic_results"]

for r in results[:3]:
    print(r["title"])
    print(r["link"])
    print(r["snippet"])
```

---

## Option 3: DuckDuckGo (Free, No API Key)

No API key needed. Good for development/testing.

```bash
pip install duckduckgo-search
```

```python
from duckduckgo_search import DDGS

with DDGS() as ddgs:
    results = list(ddgs.text("AI agents 2025", max_results=5))
    for r in results:
        print(r["title"])
        print(r["href"])
        print(r["body"])
```

---

## Comparison

| Tool | Cost | Quality | Setup | Best for |
|------|------|---------|-------|---------|
| Tavily | Free tier (1k/month) | High (LLM-optimized) | API key | Production agents |
| SerpAPI | Paid ($50/month) | Very High (real Google) | API key | When accuracy matters most |
| DuckDuckGo | Free | Medium | None | Development/testing |

---

## Reading a Specific URL

Sometimes the agent needs to read a specific webpage, not just search:

```python
import requests
from bs4 import BeautifulSoup

def read_url(url: str) -> str:
    """Fetch and extract text from a webpage."""
    response = requests.get(url, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Remove scripts and styles
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    
    return soup.get_text(separator="\n", strip=True)[:5000]  # cap at 5000 chars
```

---

## Related Notes

- [[Concepts/Tool Use & Function Calling]] — how to register search as a tool
- [[Concepts/Agent Loop - ReAct Pattern]] — where search fits in the loop
