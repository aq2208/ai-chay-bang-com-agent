# Report Format

#project

> [!info] Canonical design: **[[Projects/00 - Project Home]]**. Updated 2026-06-11: the report writer uses
> **`google/gemma-4-31b-it` via AgentBase MaaS** (the `claude-sonnet-4-6` in the code sample is historical).
> See `report/generator.py` for the implemented format (header, executive summary, issue table with
> Domain · Segment · Issue · Mentions · Sources · Suggested Approach).

---

## Report Structure (v1)

One report file per run date. Inside: one section per domain, each with a summary table + detail rows.

```
output/
└── 2026-06-10/
    └── report.md        ← single file, sections per domain
```

---

## Full Report Template

````markdown
# User Issue Report — 2026-06-10

**Generated:** 2026-06-10 08:05  
**Period:** Last 24 hours (2026-06-09 08:00 → 2026-06-10 08:00)  
**Total issues collected:** 27 (Jira: 8 | Facebook: 12 | Threads: 7)  
**After sentiment filter:** 21 negative posts retained

---

## Summary by Domain

| Domain | Issue Count | Top Issue | Severity |
|--------|------------|-----------|----------|
| Payment | 9 | Visa top-up failure (E5001) | 🔴 High |
| QR Code | 5 | QR scan failure at merchants | 🟡 Medium |
| Account | 4 | OTP not received | 🟡 Medium |
| App Performance | 3 | App crash on launch | 🔴 High |

---

## Domain: Payment

**Issues found:** 9 (Jira: 3 | Facebook: 4 | Threads: 2)

| # | Issue | Description | Domain | Segment | Sources | Mentions | Suggested Approach |
|---|-------|-------------|--------|---------|---------|----------|--------------------|
| 1 | Visa top-up failure | Users unable to top up using Visa cards; error code E5001 appears after entering card details | Payment | Top-up | FB, Jira | 6 | Check payment gateway retry config. Known fix: set retry limit to 3. See KB-42 |
| 2 | Mastercard declined | Mastercard top-up rejected without error message, transaction shows as pending | Payment | Top-up | Threads, Jira | 3 | Investigate pending transaction state in payment gateway logs. Escalate to gateway provider |
| 3 | Duplicate charge | User charged twice for single transaction; refund not reflected after 24h | Payment | Billing | Jira | 1 | Check idempotency key handling. Trigger manual refund review for affected users |

### Issue Details

#### Issue #1 — Visa top-up failure (E5001)
> "Không nạp tiền được bằng Visa, báo lỗi E5001 mà không giải thích gì hết" — Facebook, 2026-06-10 07:23  
> "Visa card top-up failing for multiple users since yesterday evening" — Jira TICKET-1234

**Root Cause (from KB):** Payment gateway timeout on Visa 3DS authentication step.  
**Suggested Approach:** Increase 3DS timeout from 10s to 30s. Add user-facing retry button. Reference: KB-42, KB-15.

---

## Domain: QR Code

| # | Issue | Description | Domain | Segment | Sources | Mentions | Suggested Approach |
|---|-------|-------------|--------|---------|---------|----------|--------------------|
| 1 | QR scan failure | QR code not scanning at Highlands Coffee locations; camera focuses but no result | QR Code | Merchant | Facebook | 3 | Check QR code version compatibility with merchant terminal firmware v2.1.3 |
| 2 | QR expired immediately | QR code shows "expired" within seconds of generation | QR Code | Payment | Threads, Jira | 2 | QR TTL may be set too short in config. Check `qr_ttl_seconds` setting |

---

## Domain: Account

...

---

## Appendix — Raw Sources

| ID | Source | Text (excerpt) | Timestamp | Sentiment | Domain |
|----|--------|----------------|-----------|-----------|--------|
| JIRA-1234 | Jira | Visa card top-up failing... | 2026-06-09 18:00 | N/A | Payment |
| FB-2045 | Facebook | Không nạp tiền được bằng Visa... | 2026-06-10 07:23 | Negative | Payment |
| TH-3012 | Threads | ZaloPay QR expired ngay lập tức... | 2026-06-10 06:10 | Negative | QR Code |
````

---

## Report Generator — Code

```python
import anthropic
from datetime import datetime

client = anthropic.Anthropic()

def generate_report(all_issues: list[dict]) -> str:
    """
    all_issues: list of enriched items after filtering, classifying, and RAG matching.
    Each item has: id, source, text, domain, segment, extracted_issue,
                   image_analysis, solution, sentiment, timestamp
    """
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Group by domain
    from collections import defaultdict
    by_domain = defaultdict(list)
    for issue in all_issues:
        by_domain[issue["domain"]].append(issue)

    # Build the data summary to pass to LLM
    domain_summaries = []
    for domain, items in by_domain.items():
        rows = []
        for i, item in enumerate(items, 1):
            rows.append(
                f"| {i} | {item['extracted_issue']} | {item['text'][:100]}... "
                f"| {item['domain']} | {item.get('segment', 'General')} "
                f"| {item['source']} | 1 | {item.get('solution', 'Investigating')} |"
            )
        domain_summaries.append({
            "domain": domain,
            "count": len(items),
            "rows": rows,
            "items": items
        })

    # Build prompt
    data_text = ""
    for ds in domain_summaries:
        data_text += f"\n### Domain: {ds['domain']} ({ds['count']} issues)\n"
        for item in ds["items"]:
            data_text += (
                f"- Source: {item['source']} | "
                f"Issue: {item['extracted_issue']} | "
                f"Segment: {item.get('segment', 'General')} | "
                f"Solution hint: {item.get('solution', 'None')} | "
                f"Text: {item['text'][:150]}\n"
            )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8096,
        system="""You are a technical writer producing issue reports for Product Owners.
Write clear, professional markdown reports.
For each domain, produce a summary table with columns:
# | Issue | Description | Domain | Segment | Sources | Mentions | Suggested Approach

Then add an Issue Details section with 1-2 sentence elaboration and solution for each issue.
Group duplicate issues together and count their mentions.
Use severity emoji: 🔴 High (5+ mentions or critical), 🟡 Medium (2-4), 🟢 Low (1).""",
        messages=[{
            "role": "user",
            "content": f"""Generate an issue report for {today}.

Period: last 24 hours
Total issues: {len(all_issues)}

Issue data:
{data_text}

Format:
1. Header with date, totals, period
2. Summary table (all domains)
3. Per-domain section with table + issue details
4. Appendix with raw sources table"""
        }]
    )

    return response.content[0].text


def save_report(content: str, date: str = None) -> str:
    """Save report to output folder, return file path."""
    import os
    date = date or datetime.now().strftime("%Y-%m-%d")
    folder = f"output/{date}"
    os.makedirs(folder, exist_ok=True)
    path = f"{folder}/report.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
```

---

## Table Columns Explained

| Column | What it contains |
|--------|----------------|
| **#** | Issue number within domain |
| **Issue** | Short name of the issue (5–8 words) |
| **Description** | What the user is experiencing — clear, factual |
| **Domain** | Top-level category (Payment, QR Code, Account...) |
| **Segment** | Sub-category (Top-up, Transfer, Login, Merchant...) |
| **Sources** | Which platforms reported this (Jira, FB, Threads) |
| **Mentions** | How many unique reports of this issue |
| **Suggested Approach** | Action for the team, from KB or LLM reasoning |

---

## Domain & Segment Reference

| Domain | Segments |
|--------|---------|
| Payment | Top-up, Transfer, Withdrawal, Billing |
| QR Code | Merchant, Payment, Generation |
| Account | Login, OTP, Registration, Profile |
| App Performance | Crash, Loading, UI Bug |
| Merchant | POS, Settlement, Onboarding |
| Other | Anything that doesn't fit above |

---

## Related Notes

- [[Projects/Architecture]] — where report generation fits in the pipeline
- [[Projects/Hackathon]] — project overview
- [[Concepts/Prompt Engineering]] — how to prompt the report writer LLM
