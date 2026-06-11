"""
Provider-LLM smoke test — verifies the project runs on VNG AgentBase MaaS (Gemma).

Run:
    .venv/bin/python smoke_test.py

Checks, in order:
  1. MaaS text  — one Gemma chat call
  2. MaaS vision — one image call (confirms the endpoint accepts image content for Gemma)
  3. Pipeline   — jira job on mock data (dry_run) end-to-end via MaaS
  4. Agentic Q&A — query the issues indexed by step 3
"""

import json

import config
from llm_client import llm

print(f"provider={config.LLM_PROVIDER}  base={config.LLM_BASE_URL[:45]}  model={config.MODEL_FAST}")
print("=" * 70)

# 1) TEXT
print("\n[1/4] MaaS TEXT")
try:
    print("  OK:", repr(llm.chat(system="Reply with exactly one word: hello", user="go", max_tokens=10)))
except Exception as e:
    print("  FAILED:", type(e).__name__, str(e)[:300])

# 2) VISION (1x1 red PNG — confirms the endpoint accepts image content)
print("\n[2/4] MaaS VISION")
red_1x1 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42m"
           "P8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
try:
    out = llm.vision(
        system="You describe images.",
        prompt="What is in this image? One short sentence.",
        images=[{"type": "base64", "data": red_1x1, "media_type": "image/png"}],
        max_tokens=40,
    )
    print("  OK:", repr(out))
except Exception as e:
    print("  FAILED:", type(e).__name__, str(e)[:400])

# 3) PIPELINE (jira mock, end-to-end via MaaS)
print("\n[3/4] PIPELINE — jira dry_run")
try:
    from main import handle_payload
    res = handle_payload({"action": "run", "job": "jira", "dry_run": True})
    print(json.dumps(res, indent=2, default=str)[:1500])
except Exception as e:
    print("  FAILED:", type(e).__name__, str(e)[:400])

# 4) Q&A
print("\n[4/4] AGENTIC Q&A")
try:
    from main import handle_payload
    q = handle_payload({"action": "query", "question": "What payment issues are users reporting?"})
    print("  status:", q.get("status"))
    print("  answer:", q.get("answer"))
except Exception as e:
    print("  FAILED:", type(e).__name__, str(e)[:400])

print("\n" + "=" * 70 + "\nDONE")
