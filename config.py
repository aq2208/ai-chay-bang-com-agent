from dotenv import load_dotenv
import os

load_dotenv()

# ── LLM Provider ──────────────────────────────────────────────────────────
# Supported: anthropic | google | openai
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
LLM_API_KEY  = os.getenv("LLM_API_KEY", "")

# Default model names per provider — override via MODEL_FAST / MODEL_SMART in .env
_MODEL_DEFAULTS: dict[str, tuple[str, str]] = {
    "anthropic": ("claude-haiku-4-5-20251001", "claude-sonnet-4-6"),
    "google":    ("gemini-2.5-flash-lite",        "gemini-2.5-pro"),
    "openai":    ("gpt-4o-mini",                "gpt-4o"),
}
_fast_default, _smart_default = _MODEL_DEFAULTS.get(LLM_PROVIDER, _MODEL_DEFAULTS["anthropic"])
MODEL_FAST  = os.getenv("MODEL_FAST",  _fast_default)   # cheap — classification, extraction
MODEL_SMART = os.getenv("MODEL_SMART", _smart_default)  # capable — report writing, image analysis

# ── Other credentials ────────────────────────────────────────────────────
JIRA_URL        = os.getenv("JIRA_URL", "")
JIRA_EMAIL      = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN  = os.getenv("JIRA_API_TOKEN", "")
FB_PAGE_ID      = os.getenv("FB_PAGE_ID", "")
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
    "ví zalopay",
    "nạp tiền lỗi",
    "thanh toán lỗi",
    "zalo pay",
]

# ── Pipeline Settings ─────────────────────────────────────────────────────
SENTIMENT_THRESHOLD      = 0.75   # below this → ask LLM as tiebreaker
GROUPING_THRESHOLD       = 0.82   # cosine similarity to merge issues
KB_SIMILARITY_THRESHOLD  = 0.48   # cosine similarity floor to accept a KB match
DAYS_BACK                = 1      # how many days back to fetch data

# ── Server & Scheduler ────────────────────────────────────────────────────
HOST                     = os.getenv("HOST", "0.0.0.0")
PORT                     = int(os.getenv("PORT", "8000"))
JIRA_SCHEDULE_HOUR       = int(os.getenv("JIRA_SCHEDULE_HOUR", "8"))
JIRA_SCHEDULE_MINUTE     = int(os.getenv("JIRA_SCHEDULE_MINUTE", "0"))
SOCIAL_SCHEDULE_HOUR     = int(os.getenv("SOCIAL_SCHEDULE_HOUR", "8"))
SOCIAL_SCHEDULE_MINUTE   = int(os.getenv("SOCIAL_SCHEDULE_MINUTE", "30"))
