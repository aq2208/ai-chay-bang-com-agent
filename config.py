from dotenv import load_dotenv
import os

load_dotenv(override=True)

# ── LLM Provider ──────────────────────────────────────────────────────────
# Supported: anthropic | google | openai
#   • Local/Colab development → google (Gemini free tier)
#   • AgentBase deployment    → openai + LLM_BASE_URL (VNG MaaS, OpenAI-compatible)
#
# AgentBase MaaS is OpenAI-compatible: set LLM_PROVIDER=openai, point LLM_BASE_URL at
# the MaaS endpoint, and use the single platform model for both fast/smart tiers:
#   LLM_PROVIDER=openai
#   LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1
#   LLM_API_KEY=<MaaS key from /agentbase-llm>
#   MODEL_FAST=google/gemma-4-31b-it
#   MODEL_SMART=google/gemma-4-31b-it
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_API_KEY  = os.getenv("LLM_API_KEY", "")
# OpenAI-compatible base URL. Empty → default OpenAI servers. Set to the MaaS endpoint
# (or any OpenAI-compatible gateway) to route the openai provider elsewhere.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")

# Default model names per provider — override via MODEL_FAST / MODEL_SMART in .env.
# For the openai provider on AgentBase MaaS, both tiers collapse to the single platform
# model (Gemma 4 31B-IT); override with MODEL_FAST/MODEL_SMART when running real OpenAI.
_MODEL_DEFAULTS: dict[str, tuple[str, str]] = {
    "anthropic": ("claude-haiku-4-5-20251001", "claude-sonnet-4-6"),
    # gemini-2.5-pro is blocked on the free tier (limit: 0) — use flash for SMART so
    # local/Colab dev works without a paid plan.
    "google":    ("gemini-2.5-flash-lite",     "gemini-2.5-flash"),
    "openai":    ("google/gemma-4-31b-it",      "google/gemma-4-31b-it") if LLM_BASE_URL
                 else ("gpt-4o-mini",           "gpt-4o"),
}
_fast_default, _smart_default = _MODEL_DEFAULTS.get(LLM_PROVIDER, _MODEL_DEFAULTS["anthropic"])
MODEL_FAST  = os.getenv("MODEL_FAST",  _fast_default)   # cheap — classification, extraction
MODEL_SMART = os.getenv("MODEL_SMART", _smart_default)  # capable — report writing, image analysis

# ── Other credentials ────────────────────────────────────────────────────
JIRA_URL        = os.getenv("JIRA_URL", "")
JIRA_EMAIL      = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN  = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT    = os.getenv("JIRA_PROJECT", "")   # optional project key to scope the JQL
JIRA_JQL        = os.getenv("JIRA_JQL", "")        # optional full JQL override
# Accept both FB_PAGE_IDS (preferred, comma-separated) and the legacy singular FB_PAGE_ID.
FB_PAGE_IDS     = [
    pid.strip()
    for pid in (os.getenv("FB_PAGE_IDS") or os.getenv("FB_PAGE_ID", "")).split(",")
    if pid.strip()
]
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN", "")
THREADS_TOKEN   = os.getenv("THREADS_ACCESS_TOKEN", "")

# ── Domain & Segment Taxonomy ─────────────────────────────────────────────
DOMAINS = [
    "Payment",
    "QR Code",
    "Account",
    "App Performance",
    "Merchant",
    "Other",
]

SEGMENTS: dict[str, list[str]] = {
    "Payment":         ["Top-up", "Transfer", "Withdrawal", "Billing"],
    "QR Code":         ["Payment", "Generation", "Merchant"],
    "Account":         ["Login", "OTP", "Registration", "Profile"],
    "App Performance": ["Crash", "Loading", "UI Bug"],
    "Merchant":        ["POS", "Settlement", "Onboarding"],
    "Other":           ["General"],
}

# ── Social Media Keywords ─────────────────────────────────────────────────
KEYWORDS = [
    "zalopay",
    "zalo pay",
    "ví zalopay",
    "ví zalo",
    "ví điện tử zalo"
]

# ── Pipeline Settings ─────────────────────────────────────────────────────
SENTIMENT_THRESHOLD      = 0.75   # below this → ask LLM as tiebreaker
GROUPING_THRESHOLD       = 0.82   # cosine similarity to merge issues
KB_SIMILARITY_THRESHOLD  = 0.48   # cosine similarity floor to accept a KB match
DAYS_BACK                = 1      # how many days back to fetch data
SCROLL_TIMES             = 4      # how many times to scroll down to load search results


# ── Server & Scheduler ────────────────────────────────────────────────────
HOST                     = os.getenv("HOST", "0.0.0.0")
PORT                     = int(os.getenv("PORT", "8080"))
JIRA_SCHEDULE_HOUR       = int(os.getenv("JIRA_SCHEDULE_HOUR", "8"))
JIRA_SCHEDULE_MINUTE     = int(os.getenv("JIRA_SCHEDULE_MINUTE", "0"))
SOCIAL_SCHEDULE_HOUR     = int(os.getenv("SOCIAL_SCHEDULE_HOUR", "8"))
SOCIAL_SCHEDULE_MINUTE   = int(os.getenv("SOCIAL_SCHEDULE_MINUTE", "30"))
