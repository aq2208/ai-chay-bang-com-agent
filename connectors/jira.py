"""
Jira connector — fetches recent complaint tickets via the Jira REST API.

Returns items shaped like the rest of the pipeline expects:
    {"id", "source": "jira", "text", "images", "timestamp"}

Config (config.py / .env):
    JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN  — required
    JIRA_PROJECT                          — optional project key to scope the search
    JIRA_JQL                              — optional full JQL override (takes precedence)
    DAYS_BACK                             — lookback window
"""

from __future__ import annotations

import os
import config

def _build_jql() -> str:
    if config.JIRA_JQL:
        return config.JIRA_JQL
    clauses = [f"created >= -{config.DAYS_BACK}d", "issuetype in (Bug, Incident)"]
    if config.JIRA_PROJECT:
        clauses.insert(0, f'project = "{config.JIRA_PROJECT}"')
    return " AND ".join(clauses) + " ORDER BY created DESC"


def _description_text(description) -> str:
    """Coerce a Jira description (string, None, or ADF dict) into plain text."""
    if not description:
        return ""
    if isinstance(description, str):
        return description
    # Atlassian Document Format (cloud, REST v3): walk text nodes.
    parts: list[str] = []

    def _walk(node):
        if isinstance(node, dict):
            if node.get("type") == "text" and node.get("text"):
                parts.append(node["text"])
            for child in node.get("content", []) or []:
                _walk(child)
        elif isinstance(node, list):
            for child in node:
                _walk(child)

    _walk(description)
    return " ".join(parts)


def fetch() -> list[dict]:
    """Fetch recent Zalopay complaint tickets from Jira."""
    url = os.getenv("JIRA_URL") or config.JIRA_URL
    email = os.getenv("JIRA_EMAIL") or config.JIRA_EMAIL
    token = os.getenv("JIRA_API_TOKEN") or config.JIRA_API_TOKEN

    if not url or not email or not token or url == "https://your-company.atlassian.net" or token == "...":
        raise RuntimeError(
            "Jira credentials not configured. "
            "Set JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env — or use dry_run=True."
        )

    from jira import JIRA

    client = JIRA(server=url, basic_auth=(email, token))
    issues = client.search_issues(_build_jql(), maxResults=200)

    items: list[dict] = []
    for issue in issues:
        f = issue.fields
        summary = f.summary or ""
        body = _description_text(getattr(f, "description", None))
        text = f"{summary}\n{body}".strip()
        items.append({
            "id":        issue.key,
            "source":    "jira",
            "text":      text,
            "images":    [],  # attachments not pulled in v1
            "timestamp": getattr(f, "created", ""),
        })
    return items

