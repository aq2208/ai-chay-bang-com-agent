"""
AgentBase Custom Agent entrypoint — ZaloPay Issue Analytics Agent.

Deployed on VNG AgentBase as a request/response Custom Agent. The platform invokes
`handler` via POST /invocations (port 8080) and calls `health` for liveness.

Payload protocol (single entrypoint, dispatched on "action"):

  Run a pipeline job:
    {"action": "run", "job": "jira" | "social" | "all", "dry_run": false}
      → fetches, processes, generates a report, and indexes the issues for Q&A.
      → returns {"status", "results": {job: {report_path, issues, mentions}}}

  Ask a question (agentic Q&A over indexed issues):
    {"action": "query", "question": "summarize payment issues this week"}
      → RAG over the issues store → grounded answer.
      → returns {"status", "answer": "..."}

LLM access is via the OpenAI-compatible MaaS endpoint (see config.py / .env):
  LLM_PROVIDER=openai, LLM_BASE_URL=<maas>/v1, MODEL_*=google/gemma-4-31b-it

Local dev: the FastAPI harness lives in local_api.py. This file is what ships.
Requires the greennode-agentbase SDK (Python 3.10+).
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

_VALID_JOBS = ("jira", "social", "all")


def handle_payload(payload: dict) -> dict:
    """
    Core dispatch — pure function, importable/testable without the AgentBase SDK.

    Returns a JSON-serializable dict. Never raises for normal control flow; errors
    are returned as {"status": "error", "message": ...} so the runtime gets a clean
    response instead of a 500.
    """
    if not isinstance(payload, dict):
        return {"status": "error", "message": "Payload must be a JSON object."}

    action = str(payload.get("action") or "run").lower()

    if action == "run":
        return _run(payload)
    if action == "query":
        return _query(payload)
    return {
        "status": "error",
        "message": f"Unknown action '{action}'. Use 'run' or 'query'.",
    }


def _run(payload: dict) -> dict:
    job = str(payload.get("job") or "all").lower()
    if job not in _VALID_JOBS:
        return {"status": "error", "message": f"Invalid job '{job}'. Use one of {_VALID_JOBS}."}

    dry_run = bool(payload.get("dry_run", False))

    # Imported lazily so the query path and `health` don't pay the heavy ML import cost.
    from jobs import jira_job, social_job

    runners = {"jira": jira_job.run, "social": social_job.run}
    selected = ["jira", "social"] if job == "all" else [job]

    results: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for name in selected:
        try:
            results[name] = runners[name](dry_run=dry_run)
        except Exception as exc:  # one job failing must not abort the other
            errors[name] = str(exc)

    out = {"status": "ok" if not errors else "partial", "dry_run": dry_run, "results": results}
    if errors:
        out["errors"] = errors
    return out


def _query(payload: dict) -> dict:
    question = str(payload.get("question") or "").strip()
    if not question:
        return {"status": "error", "message": "Provide a 'question' to query."}

    from knowledge_base.issues_store import answer_question

    answer = answer_question(question)
    return {"status": "ok", "question": question, "answer": answer}


# ── AgentBase wiring ────────────────────────────────────────────────────────
# Guarded so this module stays importable (for tests) even where the SDK is absent.
try:
    from greennode_agentbase import GreenNodeAgentBaseApp, RequestContext, PingStatus

    app = GreenNodeAgentBaseApp()

    @app.entrypoint
    def handler(payload: dict, context: "RequestContext") -> dict:
        return handle_payload(payload)

    @app.ping
    def health() -> "PingStatus":
        return PingStatus.HEALTHY

    if __name__ == "__main__":
        app.run(port=8080, host="0.0.0.0")

except ImportError:  # SDK not installed (e.g. local Python 3.9 dev shell)
    app = None

    if __name__ == "__main__":
        raise SystemExit(
            "greennode-agentbase is not installed (needs Python 3.10+).\n"
            "Install it to run the AgentBase server, or test the dispatch logic with:\n"
            "    from main import handle_payload"
        )
