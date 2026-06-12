# AgentBase Platform Guide

#agentbase #vng-hackathon

A practical, end-to-end reference for planning, developing, and deploying AI agents on VNG's AgentBase platform. Built from a real onboarding session — includes real commands, gotchas, and decisions made along the way.

**Related:** [[Projects/2026-06-10-agentbase-sample-agent-design]] | [[Projects/Hackathon]]

---

## Real Workflow — How to Actually Do This

This is the short version. Use the slash command skills and you can go from zero to deployed agent with very few manual steps.

### Step 1 — Install the Skills

```bash
# Clone the skills repo (anywhere on your machine)
git clone https://github.com/vngcloud/greennode-agentbase-skills.git

# Copy into your project (project-scoped — only active in this folder)
mkdir -p <your-project>/.claude/skills
cp -r greennode-agentbase-skills/.claude/skills/. <your-project>/.claude/skills/
```

Restart Claude Code. Skills appear as slash commands automatically.

> **Gotcha (zsh):** Use `.` not `*` at the end of `cp` — zsh glob expansion fails on `*` when copying directories.
> **Project-scoped vs global:** Copying to `~/.claude/skills/` makes skills global. Copying to `<project>/.claude/skills/` scopes them to that project only.

---

### Step 2 — Configure Credentials

Create `.greennode.json` manually in your project root (create in editor, not terminal):

```json
{
  "client_id": "<your-service-account-id>",
  "client_secret": "<your-service-account-secret>",
  "agent_identity": ""
}
```

```bash
echo ".greennode.json" >> .gitignore
```

This is the SDK-native credential format — works for all AgentBase scripts without needing `export`. Get credentials from `iam.console.vngcloud.vn/service-accounts`.

Verify:
```bash
bash .claude/skills/agentbase/scripts/check_credentials.sh iam
```

---

### Path A — Full Wizard (recommended for first-time users)

```
/agentbase-wizard
```

That's it. The wizard guides you through all 9 steps:

1. Check credentials
2. Scaffold project files (`main.py`, `Dockerfile`, `requirements.txt`, etc.)
3. Set up Memory (optional)
4. Set up Identity & external auth (optional)
5. Customize agent code
6. Configure env vars including LLM access
7. Local testing
8. Build → push → deploy
9. Verify endpoint is live

You can resume a stopped wizard: `/agentbase-wizard resume`
Jump to a step: `/agentbase-wizard step-N`
Clear state and restart: `/agentbase-wizard reset`

---

### Path B — Write Your Own Code + Deploy Skill

For developers who want full control or are using a specific framework (CrewAI, LlamaIndex, LangGraph, etc.):

**1. Write your agent** using the `greennode-agentbase` SDK:

```python
from greennode_agentbase import GreenNodeAgentBaseApp, RequestContext, PingStatus

app = GreenNodeAgentBaseApp()

@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    # Your logic here
    return {"message": "Hello from my agent"}

@app.ping
def health() -> PingStatus:
    return PingStatus.HEALTHY

if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
```

**2. Create a Dockerfile:**

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python", "main.py"]
```

**3. Configure LLM access** (if your agent calls an LLM):

```
/agentbase-llm
```

This lists available models and creates/manages an API key. Add to `.env`:

```
LLM_API_KEY=<your-key>
LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1
LLM_MODEL=google/gemma-4-31b-it
```

Then call the LLM from code using the standard OpenAI SDK (the platform endpoint is OpenAI-compatible):

```python
from openai import OpenAI
import os

client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ["LLM_BASE_URL"])
response = client.chat.completions.create(
    model=os.environ["LLM_MODEL"],
    messages=[{"role": "user", "content": message}],
)
```

**4. Deploy:**

```
/agentbase-deploy
```

The skill asks you for: registry choice, runtime name, compute flavor, env file path. Then handles CR login → build → push → create runtime → poll until ACTIVE → return endpoint URL.

---

## What is AgentBase?

VNG's AI Portal (`aiplatform.console.vngcloud.vn`) is an all-in-one platform to build, deploy, and manage AI agents. You bring the code (or use templates) — the platform handles the infrastructure.

### Platform Components

| Component | What it does | Console URL |
|-----------|-------------|-------------|
| **Models (MaaS)** | Platform-hosted LLMs via OpenAI-compatible API. No external account needed, unified billing. | `/models` |
| **Agent Runtime** | Runs your agent as a Docker container with autoscaling, versioning, endpoints. | `/agent-runtime` |
| **Memory** | Short-term (conversation history) and long-term (semantic facts) memory stores. | `/memory` |
| **RAG Engine / Knowledge Base** | Index your documents and query them from agent code. | `/knowledge` |
| **Identity & Auth** | Register agent identities. Store and inject outbound API keys and OAuth2 tokens securely. | `/access-control` |
| **Guardrails** | Safety and content filtering policies for your agents. | `/guardrails` |

### Two Agent Types

| Type | What it is | When to use |
|------|-----------|-------------|
| **Custom Agent** | You write Python (or any language), package it into a Docker image, platform runs it. | Any agent with custom logic — Q&A, pipelines, tool-using agents. |
| **OpenClaw** | Pre-built template bots (Telegram / Zalo). No Docker image — just configure tokens and model. | You want a chat bot fast with no coding. |

---

## Prerequisites

- **GreenNode IAM Service Account** — go to `iam.console.vngcloud.vn/service-accounts`, create one, attach policies: `AgentBaseFullAccess`, `vcrFullAccess`, `AiPlatformFullAccess`. Copy `client_id` and `client_secret` immediately (secret shown once only).
- **Docker** — needed to build and push your agent image.
- **Python 3.10+** — required for the SDK and scaffolded projects. Install via `pyenv` if needed (see below).
- **Claude Code** — for using the AgentBase slash command skills.

### Python Version

```bash
python3 --version  # needs to be 3.10+
```

If below 3.10, install via pyenv:

```bash
brew install pyenv
pyenv install 3.13.3
pyenv global 3.13.3
```

Add to `~/.zshrc` so it activates on every shell:

```bash
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
```

### Virtual Environment

After scaffolding, the wizard creates a Python virtual environment (`venv/`) and installs dependencies into it.

**What it is:** A self-contained Python installation isolated to your project folder. It has its own `pip`, its own `site-packages`, and doesn't touch your system Python.

**What it does:**
```bash
python3 -m venv venv        # creates venv/ in your project
source venv/bin/activate    # switches your shell to use it
pip install -r requirements.txt  # installs packages into it, not system Python
```

**Why you need it:** Without a venv, `pip install` writes packages into your global Python. Two projects needing different versions of the same library will break each other. With a venv, each project is isolated.

**Do you strictly need it?** No. For a hackathon, installing directly is fine:
```bash
pip install greennode-agentbase python-dotenv
```
But once you have multiple Python projects, you'll want venvs.

> **Remember:** Run `source venv/bin/activate` once per terminal session. If you open a new terminal and `python3 main.py` fails with `ModuleNotFoundError`, it's because the venv isn't activated.

---

## Skills Reference

### `/agentbase-wizard`
**Purpose:** Guided full lifecycle — takes you from zero to deployed agent in 9 steps.

**Use when:** You're new to the platform, or want to set up all platform features (memory, identity, LLM) in a structured way.

| Command | What it does |
|---------|-------------|
| `/agentbase-wizard` | Start full wizard |
| `/agentbase-wizard init <name>` | Scaffold only, no deploy |
| `/agentbase-wizard test` | Run local/docker tests only |
| `/agentbase-wizard resume` | Continue from last completed step |
| `/agentbase-wizard step-N` | Jump to a specific step |
| `/agentbase-wizard reset` | Clear state and start fresh |

**What it covers:** Prerequisites check → project scaffold → memory setup → identity/auth → code customization → env config → local testing → deploy → verify

---

### `/agentbase-deploy`
**Purpose:** Build your Docker image, push to the Container Registry, create or update the Agent Runtime, and get an endpoint URL.

**Use when:** You've written your agent code and want to deploy it. Also use for redeploying after code changes.

**What is a Runtime?**
A Runtime is what AgentBase calls a running deployment of your agent. You push a Docker image, the platform pulls it and runs it on their infrastructure — CPU, memory, networking, autoscaling all managed by them. That running deployment is the Runtime. One Runtime = one deployed agent, with a stable endpoint URL, compute resources, auto-injected platform credentials, and version history (each redeploy creates a new version under the same Runtime).

**Key concepts:**
- Uses the **AgentBase managed Container Registry** (pre-provisioned, no setup) — recommended.
- Supports **PUBLIC** (internet-accessible) and **VPC** (private network) runtime modes.
- Creates a `DEFAULT` endpoint automatically.
- Auto-injects `GREENNODE_CLIENT_ID`, `GREENNODE_CLIENT_SECRET`, `GREENNODE_AGENT_IDENTITY` into the container — do NOT set these in your `.env`.

| Command | What it does |
|---------|-------------|
| `/agentbase-deploy` | Full deploy pipeline |
| `/agentbase-deploy cr` | Container Registry operations (login, list images, rotate credentials) |

---

### `/agentbase-llm`
**Purpose:** Get an OpenAI-compatible API key for the platform's LLM models (MaaS). Browse available models, create/manage API keys.

**Use when:** Your agent needs to call an LLM. Use the platform's LLM first (no external account needed, unified billing) before falling back to OpenAI.

**LLM endpoint:** `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1` (OpenAI-compatible)

```bash
bash .claude/skills/agentbase/scripts/aip.sh api-keys list
bash .claude/skills/agentbase/scripts/aip.sh api-keys create --name my-key
bash .claude/skills/agentbase/scripts/aip.sh models list --status ENABLED
bash .claude/skills/agentbase/scripts/aip.sh models enable MODEL_UUID
```

> **Use the model's `path` field** (not `code`) when calling the API.
> **API key creation is async** — poll until `status: ACTIVE`.

---

### `/agentbase-identity`
**Purpose:** Register an agent identity and store outbound credentials (API keys, OAuth2 tokens) that the platform injects into your agent at runtime. Avoids hardcoding external credentials.

**Use when:** Your agent calls external APIs (e.g. Jira, Slack, a database) that require authentication. For simple agents, skip this — the runtime auto-provisions a basic identity.

---

### `/agentbase-memory`
**Purpose:** Create and manage memory stores for your agent — conversation history (short-term) and semantic facts (long-term).

**Use when:** Your agent needs to remember things across messages or sessions.

- **Short-term** (conversation history): Uses `AgentBaseMemoryEvents` as a LangGraph/LangChain checkpointer. Automatically saves and restores conversation state per session.
- **Long-term** (semantic facts): Uses `MemoryClient` SDK with `remember`/`recall` tool calls. The agent can store and retrieve facts across conversations.

---

### `/agentbase-monitor`
**Purpose:** View runtime logs, CPU/RAM metrics, and debug running agents.

**Use when:** Your agent is deployed and you want to check logs, diagnose errors, or monitor resource usage.

```
/agentbase-monitor runtime-logs
```

---

### `/agentbase-gateway`
**Purpose:** Manage Resource Gateways (MCP servers) — expose external tools/resources to your agents via the Model Context Protocol.

**Use when:** You want your agent to call external services through a managed MCP interface.

---

### `/agentbase-policy`
**Purpose:** Manage authorization and access control policies — who can call your agent, what they can do.

**Use when:** You need to restrict agent access or define permission rules for multi-user scenarios.

---

### `/agentbase-teardown`
**Purpose:** Delete all resources for a project — runtime, endpoints, memory, identity, registry images.

**Use when:** Cleaning up after a demo, removing a test project, or starting fresh.

> **Warning:** Destructive and irreversible. Confirm carefully before running.

---

### `/agentbase`
**Purpose:** Platform architecture reference — explains how components fit together, authentication setup, SDK imports, API endpoints.

**Use when:** You have a general question about how the platform works, or which skill to use for a task.

---

## Under the Hood — What the Skills Do

This section shows the individual commands that `/agentbase-wizard` and `/agentbase-deploy` run on your behalf. Useful if you want to understand what's happening, or if you need to do a specific step manually.

### Credentials & Config

**`.greennode.json` vs `.env` — What Goes Where:**

| File | What goes in it | Why |
|------|----------------|-----|
| `.greennode.json` | `client_id`, `client_secret`, `agent_identity` | Platform auth — how your agent authenticates with GreenNode's APIs. Owned by the SDK. |
| `.env` | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, and any other app config | Runtime config — values your agent code reads at startup. |

**Rule of thumb:** If it's about accessing the GreenNode platform → `.greennode.json`. If it's about your agent's own configuration → `.env`.

The LLM API key goes in `.env` because it's a credential for calling the model API — a service your agent uses, not the platform itself.

Both files must be gitignored:
```bash
echo ".greennode.json" >> .gitignore
echo ".env" >> .gitignore
```

> **On AgentBase Runtime:** When deployed, the platform auto-injects `GREENNODE_CLIENT_ID`, `GREENNODE_CLIENT_SECRET`, and `GREENNODE_AGENT_IDENTITY` into your container. You don't need to manage these in production — only for local dev.

### LLM Access Setup

**Get an API Key:**

```bash
bash .claude/skills/agentbase/scripts/aip.sh api-keys create --name my-agent-key
# poll until ACTIVE:
bash .claude/skills/agentbase/scripts/aip.sh api-keys get my-agent-key
```

Or via portal: `https://aiplatform.console.vngcloud.vn/models` → API Keys → Create

> Key name: lowercase letters, digits, hyphens only, 5–50 chars.

**Browse models:**

```bash
bash .claude/skills/agentbase/scripts/aip.sh models list --status ENABLED
```

Available models (as of June 2026): **Gemma 4 31B-IT** (`google/gemma-4-31b-it`) — multimodal, 128K context, good for general Q&A.

**Configure `.env`:**

```
LLM_API_KEY=<your-key>
LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1
LLM_MODEL=google/gemma-4-31b-it
```

Verify: `bash .claude/skills/agentbase/scripts/check_credentials.sh llm`

**Test locally:**

```bash
python3 main.py
# in another terminal:
curl -X POST http://127.0.0.1:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the capital of France?"}'
```

### Deploy Steps (Manual)

These are the individual steps `/agentbase-deploy` runs for you.

**1. Login to AgentBase Container Registry:**

```bash
bash .claude/skills/agentbase/scripts/cr.sh credentials docker-login
```

Credentials are fetched in-memory and piped to `docker login --password-stdin`. Nothing is written to disk.

**2. Build the image:**

```bash
docker build --platform linux/amd64 \
  -t vcr.vngcloud.vn/<repo-name>/<agent-name>:v$(date +%Y%m%d%H%M%S) .
```

> **Always use `--platform linux/amd64`** on Apple Silicon — AgentBase Runtime runs on amd64. Without this, the image builds for arm64 and the container fails to start silently.

**3. Push the image:**

```bash
docker push vcr.vngcloud.vn/<repo-name>/<agent-name>:<tag>
```

**4. Create the runtime:**

```bash
bash .claude/skills/agentbase/scripts/runtime.sh create \
  --name "<agent-name>" \
  --image "vcr.vngcloud.vn/<repo-name>/<agent-name>:<tag>" \
  --flavor "runtime-s2-general-2x4" \
  --env-file .env \
  --min-replicas 1 --max-replicas 1 \
  --cpu-scale 50 --mem-scale 50 \
  --from-cr
```

Key flags:
- `--from-cr` — pull image credentials from the managed CR (no credentials file needed)
- `--env-file` — injects your `.env` into the container at runtime
- `--flavor` — compute size: `runtime-s2-general-2x4` (2CPU/4GB), `runtime-s2-general-4x8` (4CPU/8GB)

> **Do NOT include** `GREENNODE_CLIENT_ID`, `GREENNODE_CLIENT_SECRET`, `GREENNODE_AGENT_IDENTITY`, or `GREENNODE_ENDPOINT_URL` in your `.env` — the platform auto-injects these.

**5. Get endpoint and verify:**

```bash
bash .claude/skills/agentbase/scripts/runtime.sh endpoints list <runtime-id>
curl -s -o /dev/null -w "%{http_code}" "<endpoint-url>/health"
```

Expected: `200`. Then test a real message:

```bash
curl -X POST "<endpoint-url>/invocations" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the capital of France?"}'
```

**Redeployment (after code changes):**

Build a new image with a new tag, push it, then update the runtime:

```bash
bash .claude/skills/agentbase/scripts/runtime.sh update <runtime-id> \
  --image "vcr.vngcloud.vn/<repo-name>/<agent-name>:<new-tag>" \
  --flavor "runtime-s2-general-2x4" \
  --env-file .env \
  --from-cr
```

---

## Gotchas & Non-Obvious Things

| Gotcha | Detail |
|--------|--------|
| **`cp` glob fails in zsh** | Use `.` instead of `*` when copying skill directories: `cp -r src/.` not `cp -r src/*` |
| **`.env` variables not visible to scripts** | Use `export` in `.env` files, or use `.greennode.json` instead — it avoids the issue entirely |
| **Python version** | Platform requires 3.10+. System Python on macOS is often 3.9. Use `pyenv`. After install, add `pyenv init` to `~/.zshrc` or it won't activate in new shells. |
| **Virtual environment** | Optional but recommended. For a hackathon, `pip install greennode-agentbase python-dotenv` directly is fine. Run `source venv/bin/activate` once per terminal session. |
| **Don't set auto-injected vars in `.env`** | `GREENNODE_CLIENT_ID`, `GREENNODE_CLIENT_SECRET`, `GREENNODE_AGENT_IDENTITY`, `GREENNODE_ENDPOINT_URL` are auto-injected by the runtime. Setting them manually can cause conflicts. |
| **Model `path` vs `code`** | When calling the LLM API, use the `path` field from the model detail (not `code`). If `path` is missing, fall back to `code`. |
| **API key creation is async** | After `aip.sh api-keys create`, poll `api-keys get <name>` until `status: ACTIVE`. |
| **Pagination is inconsistent** | Identity Service: 0-indexed (`page=0`). Runtime + Memory + CR: 1-indexed (`page=1`). |
| **`DEFAULT` endpoint is read-only** | You can't update it directly. To rollback, update the runtime with the old image — the DEFAULT endpoint auto-tracks the new version. |
| **Docker platform on Apple Silicon** | Build with `--platform linux/amd64` — AgentBase Runtime runs on amd64. |
| **Heredoc in terminal** | Avoid `<< 'EOF'` in terminal for creating JSON/credential files — confusing for beginners. Just create the file in your editor and fill in the values directly. |

---

## Next Steps — Real Hackathon Agent

See **[[Projects/00 - Project Home]]** for the ZaloPay Issue Analytics Agent — the real project this
onboarding feeds into.

How the real project uses the platform (as built):
- **Custom Agent** (Basic framework, plain Python) — not LangChain. Entrypoint `main.py` dispatches
  `run` / `query` on `POST /invocations`.
- **LLM via MaaS** — `google/gemma-4-31b-it`, OpenAI-compatible (`LLM_PROVIDER=openai` + `LLM_BASE_URL`).
- **RAG runs in-container** — ChromaDB (`knowledge_base` + `taxonomy` + `issues`) baked into the image,
  alongside PhoBERT + MiniLM. (Platform Memory/Knowledge Base are a future upgrade path.)
- **External APIs** (Jira / Facebook / Threads) — creds via `.env`/`--env-file` for the demo; AgentBase
  **Identity** is the cleaner long-term option.
- **Compute** — deploy on `runtime-s2-general-4x8` (4CPU/8GB) because of the bundled ML models.
