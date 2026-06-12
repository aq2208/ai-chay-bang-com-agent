# Guardrails

#concept #advanced

---

## What Guardrails Are

Guardrails are validation checks that run **after** the LLM responds to verify its output is correct, safe, and properly formatted before it reaches the user.

```
Input → [LLM] → Raw response → [Guardrails] → Validated response
                                     ↓
                              Reject / retry if fails
```

Think of it as a quality control step. The LLM might hallucinate, misformat, or produce low-quality output — guardrails catch that.

---

## Why You Need Them

Without guardrails, the LLM might:
- **Hallucinate issues** — report a problem that doesn't appear in the source data
- **Wrong format** — return prose instead of the required table
- **Missing fields** — skip the "Suggested Approach" column
- **Invent solutions** — suggest a fix not found in your knowledge base
- **Wrong domain** — assign an issue to the wrong category

---

## Types of Guardrails

### 1. Format Validation
Check that the output matches the expected structure.

```python
def validate_report_format(report_text: str) -> tuple[bool, str]:
    """Check the report has required sections."""
    required_sections = [
        "## Summary by Domain",
        "| # | Issue |",         # table header exists
        "| Domain |",
        "| Suggested Approach |"
    ]
    for section in required_sections:
        if section not in report_text:
            return False, f"Missing required section: '{section}'"
    return True, "ok"
```

### 2. Structured Output (JSON) + Schema Validation
Ask the LLM to return JSON, then validate it against a schema.

```python
from pydantic import BaseModel, validator
import json

class IssueRow(BaseModel):
    issue: str
    description: str
    domain: str
    segment: str
    sources: list[str]
    mentions: int
    suggested_approach: str

    @validator("domain")
    def valid_domain(cls, v):
        allowed = {"Payment", "QR Code", "Account", "App Performance", "Merchant", "Other"}
        if v not in allowed:
            raise ValueError(f"Unknown domain: {v}")
        return v

    @validator("mentions")
    def positive_mentions(cls, v):
        if v < 1:
            raise ValueError("Mentions must be >= 1")
        return v

def validate_issues(llm_json_output: str) -> list[IssueRow]:
    data = json.loads(llm_json_output)
    return [IssueRow(**row) for row in data]  # raises if any row is invalid
```

Prompt the LLM to return JSON:
```python
system = """You are a report writer. Return your response as a JSON array of issue objects.
Each object must have: issue, description, domain, segment, sources, mentions, suggested_approach.
Domains must be one of: Payment, QR Code, Account, App Performance, Merchant, Other."""
```

### 3. Hallucination Check
Verify that issues in the report actually appeared in the source data.

```python
def check_hallucination(report_issues: list[dict], source_items: list[dict]) -> list[str]:
    """Flag any issue in the report that has no match in source data."""
    source_texts = " ".join([item["extracted_issue"] for item in source_items]).lower()
    flags = []
    for issue in report_issues:
        keywords = issue["issue"].lower().split()
        # At least 2 keywords from the issue title must appear in source data
        matches = sum(1 for kw in keywords if kw in source_texts)
        if matches < 2:
            flags.append(f"Possible hallucination: '{issue['issue']}' — not found in source data")
    return flags
```

### 4. Completeness Check
Make sure every domain that had issues is covered in the report.

```python
def check_completeness(report_text: str, enriched_items: list[dict]) -> list[str]:
    """Check all domains with issues are in the report."""
    from collections import Counter
    domain_counts = Counter(item["domain"] for item in enriched_items)
    missing = []
    for domain in domain_counts:
        if domain not in report_text:
            missing.append(f"Domain '{domain}' has {domain_counts[domain]} issues but is missing from report")
    return missing
```

### 5. Retry on Failure
If validation fails, retry the LLM call with corrected instructions.

```python
def generate_report_with_retry(items: list[dict], max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        report = generate_report(items)

        # Run all validators
        format_ok, format_err = validate_report_format(report)
        hallucinations = check_hallucination(parse_issues(report), items)
        missing = check_completeness(report, items)

        errors = []
        if not format_ok:
            errors.append(format_err)
        errors.extend(hallucinations)
        errors.extend(missing)

        if not errors:
            return report  # passed all checks

        # Tell LLM what was wrong and retry
        print(f"Attempt {attempt+1} failed: {errors}")
        report = generate_report(items, correction_hint="\n".join(errors))

    raise RuntimeError("Report failed validation after max retries")
```

---

## Guardrails Libraries

### Option 1: Guardrails AI
```bash
pip install guardrails-ai
```
```python
from guardrails import Guard
from guardrails.hub import ValidRange, ValidChoices

guard = Guard().use_many(
    ValidChoices(choices=["Payment", "QR Code", "Account"], on_fail="fix"),
    ValidRange(min=1, max=1000, on_fail="fix")
)
validated = guard.parse(llm_output)
```

### Option 2: Pydantic (Simpler, More Control)
Just use Pydantic models to validate LLM JSON output. Simpler and often sufficient.

### Option 3: Custom Validation (Most Control)
Write your own validators as regular Python functions. Best for domain-specific checks like hallucination detection.

**For your hackathon:** Pydantic + custom validators is the right balance.

---

## Where Guardrails Fit in the Pipeline

```
enriched_items
        ↓
[LLM] generates report
        ↓
[Guardrails] ← HERE
  ├── Format check → pass/retry
  ├── Schema validation → pass/retry
  ├── Hallucination check → flag/retry
  └── Completeness check → pass/retry
        ↓
  Validated report saved to output/
```

---

## Practical Guardrail for Your Project

Minimal effective guardrail for the hackathon:

```python
def validate_report(report: str, source_items: list[dict]) -> dict:
    results = {
        "passed": True,
        "errors": [],
        "warnings": []
    }

    # 1. Format check
    if "| # | Issue |" not in report:
        results["errors"].append("Report missing issue table")
        results["passed"] = False

    # 2. Domain coverage
    expected_domains = set(item["domain"] for item in source_items)
    for domain in expected_domains:
        if domain not in report:
            results["warnings"].append(f"Domain '{domain}' may be missing from report")

    # 3. Length sanity check
    if len(report) < 500:
        results["errors"].append("Report suspiciously short — may be incomplete")
        results["passed"] = False

    return results
```

---

## Related Notes

- [[Concepts/LLM as a Processing Step]] — guardrails run after the LLM step
- [[Concepts/Prompt Engineering]] — good prompts reduce the need for guardrails
- [[Projects/Architecture]] — where guardrails fit in the pipeline
