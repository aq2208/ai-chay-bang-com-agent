"""
Phase 5 — Report guardrails.
Validates a generated markdown report for completeness and correctness
before it is saved or delivered.
"""

from __future__ import annotations

import re

_WRONG_BRAND_RE = re.compile(r"\bzalo\s*pay\b", re.IGNORECASE)
_CORRECT_BRAND = "Zalopay"


def check_report(report: str, items: list[dict]) -> dict:
    """
    Validate a generated report.

    Args:
        report: the markdown string from generate_report()
        items:  the enriched pipeline items that were used to build it

    Returns:
        {"ok": bool, "issues": [str]}
        ok=True means the report passed all checks.
    """
    problems: list[str] = []

    if not report.startswith("# Zalopay Complaint Report"):
        problems.append("Missing report title")

    if items:
        if "## Executive Summary" not in report:
            problems.append("Missing Executive Summary section")

        if "| Domain | Segment | Issue |" not in report:
            problems.append("Missing issue table header row")

        data_rows = [
            line for line in report.splitlines()
            if line.startswith("| ")
            and "Domain" not in line
            and line.strip().startswith("|")
            and "---" not in line
        ]
        if not data_rows:
            problems.append("Items provided but no table rows found in report")

    expected_domains = {item.get("domain", "Other") for item in items}
    for domain in expected_domains:
        if domain not in report:
            problems.append(f"Domain '{domain}' appears in items but not in report")

    wrong = [m.group() for m in _WRONG_BRAND_RE.finditer(report) if m.group() != _CORRECT_BRAND]
    if wrong:
        problems.append(f"Incorrect brand name casing found: {list(set(wrong))}")

    return {"ok": len(problems) == 0, "issues": problems}
