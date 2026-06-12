# Image Processing with Gemma Vision

#project #concept

> [!info] Canonical design: **[[Projects/00 - Project Home]]**. Updated 2026-06-11: vision now uses
> **`google/gemma-4-31b-it` (multimodal) via AgentBase MaaS**, called through `llm_client.vision()` with
> **OpenAI-style `image_url` content** (URL or base64 data-URI). The Claude examples below illustrate the
> same idea; the implemented path is the OpenAI-compatible one. ⚠️ Verify the MaaS endpoint accepts image
> content for Gemma — if not, image analysis degrades to text-only (pipeline still works).

---

## The Good News

Gemma 4 (and the `llm_client` abstraction) handle images natively. No separate vision model, no extra
API — pass the image as an `image_url` content block. The examples below use Claude's block format to
explain the concept; in code we use `llm.vision(images=[{"type":"url"|"base64", ...}])` which builds the
right format for the active provider.

---

## How Claude Reads Images

```python
import anthropic
import base64

client = anthropic.Anthropic()

# Option 1: From URL (easiest for social media)
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": "https://example.com/screenshot.png"
                }
            },
            {
                "type": "text",
                "text": "What issue is shown in this screenshot?"
            }
        ]
    }]
)
print(response.content[0].text)

# Option 2: From file (base64 encoded)
with open("screenshot.png", "rb") as f:
    image_data = base64.standard_b64encode(f.read()).decode("utf-8")

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",   # image/jpeg, image/gif, image/webp
                    "data": image_data
                }
            },
            {"type": "text", "text": "What issue is shown in this screenshot?"}
        ]
    }]
)
```

---

## Comparing with Sample Images

The key use case: a user posts a screenshot → compare with your team's sample images → identify which known issue this is.

```python
def analyze_post_image(post_image_url: str, sample_images: list[dict]) -> dict:
    """
    post_image_url: URL of the user's screenshot from social media
    sample_images: list of {"url": "...", "label": "E5001 payment error", "domain": "Payment"}
    """

    # Build the message content
    content = []

    # Add the user's image
    content.append({
        "type": "image",
        "source": {"type": "url", "url": post_image_url}
    })
    content.append({
        "type": "text",
        "text": "This is a screenshot posted by a user on social media. Analyze it.\n\nNow compare it with these known issue samples:"
    })

    # Add each sample image
    for i, sample in enumerate(sample_images):
        content.append({
            "type": "image",
            "source": {"type": "url", "url": sample["url"]}
        })
        content.append({
            "type": "text",
            "text": f"Sample {i+1}: {sample['label']} (Domain: {sample['domain']})"
        })

    # Ask for analysis
    content.append({
        "type": "text",
        "text": """Based on the user's screenshot and the samples above, answer:
1. What issue is the user experiencing? (describe clearly)
2. Which sample does it most closely match? (give the label)
3. Which domain does this belong to?
4. Confidence: high / medium / low

Reply in JSON format:
{
  "issue_description": "...",
  "matched_sample": "...",
  "domain": "...",
  "confidence": "high|medium|low"
}"""
    })

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": content}]
    )

    import json
    text = response.content[0].text
    # Extract JSON from response
    start = text.find("{")
    end = text.rfind("}") + 1
    return json.loads(text[start:end])


# Usage
result = analyze_post_image(
    post_image_url="https://facebook.com/photo/123.jpg",
    sample_images=[
        {"url": "samples/e5001_error.png", "label": "E5001 payment error", "domain": "Payment"},
        {"url": "samples/qr_fail.png",     "label": "QR code scan failure", "domain": "QR Code"},
        {"url": "samples/login_fail.png",  "label": "Login failure screen",  "domain": "Account"},
    ]
)

# result:
# {
#   "issue_description": "Payment declined screen with error code E5001",
#   "matched_sample": "E5001 payment error",
#   "domain": "Payment",
#   "confidence": "high"
# }
```

---

## Full Processor for a Social Media Post

```python
def process_post(post: dict, sample_images: list[dict]) -> dict:
    """
    Takes a raw social media post (with optional image),
    returns enriched version with image analysis.
    """
    enriched = post.copy()

    if post.get("images"):
        # Analyze the first image (can extend to multiple)
        image_url = post["images"][0]
        analysis = analyze_post_image(image_url, sample_images)

        enriched["image_analysis"] = analysis["issue_description"]
        enriched["matched_sample"] = analysis["matched_sample"]
        enriched["domain"] = analysis["domain"]
        enriched["image_confidence"] = analysis["confidence"]
    else:
        enriched["image_analysis"] = None

    return enriched
```

---

## Practical Tips

### Tip 1: Load sample images once at startup
Don't reload sample images on every call. Load them into memory at startup as base64 strings.

```python
import base64

def load_sample_images(folder: str) -> list[dict]:
    samples = []
    for path in Path(folder).glob("*.png"):
        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")
        label = path.stem.replace("_", " ")
        domain = path.parent.name
        samples.append({
            "data": data,
            "media_type": "image/png",
            "label": label,
            "domain": domain
        })
    return samples
```

### Tip 2: Use Haiku for simple classification, Sonnet for complex analysis

```python
# Simple: "is there an error code visible?" → Haiku (fast, cheap)
# Complex: "compare with 5 samples and identify the issue" → Sonnet
```

### Tip 3: Handle posts with no image gracefully

```python
if not post.get("images"):
    # Fall back to text-only analysis
    domain = classify_domain_from_text(post["text"])
```

### Tip 4: Token cost for images

Each image uses ~1,600 tokens (for standard size). With 5 sample images + 1 user image per post, that's ~9,600 tokens per image-analysis call. Keep sample set small (5–10 images).

---

## Image Formats Supported

| Format | Media Type |
|--------|-----------|
| JPEG | `image/jpeg` |
| PNG | `image/png` |
| GIF | `image/gif` |
| WebP | `image/webp` |

Max image size: 5MB per image.

---

## Sample Images — Folder Structure

```
sample_images/
├── Payment/
│   ├── e5001_payment_declined.png
│   ├── timeout_error.png
│   └── card_not_supported.png
├── QR_Code/
│   ├── qr_scan_failure.png
│   └── qr_expired.png
├── Account/
│   ├── login_failure.png
│   └── otp_not_received.png
└── App_Performance/
    └── loading_spinner_stuck.png
```

---

## Related Notes

- [[Projects/Architecture]] — where image processing fits in the pipeline
- [[Projects/Hackathon]] — project overview
- [[Concepts/LLM API Basics]] — Claude API fundamentals
