"""
Pluggable LLM client — change LLM_PROVIDER in .env to swap providers.

Supported providers:
  anthropic  →  Claude (requires: pip install anthropic)
  google     →  Gemini (requires: pip install google-genai)
  openai     →  OpenAI / any OpenAI-compatible API (requires: pip install openai)

Usage:
    from llm_client import llm

    # Text only
    text = llm.chat(system="...", user="...", max_tokens=60)
    text = llm.chat(system="...", user="...", max_tokens=200, fast=False)  # smart model

    # Text + images (vision)
    text = llm.vision(
        system="Describe the issue.",
        prompt="What error is shown?",
        images=[
            {"type": "url",    "url": "https://..."},
            {"type": "base64", "data": "...", "media_type": "image/png"},
        ],
        max_tokens=300,
    )
"""

from __future__ import annotations
from config import LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, MODEL_FAST, MODEL_SMART


def _openai_client():
    """Build an OpenAI client, routing to LLM_BASE_URL when set (e.g. VNG MaaS)."""
    from openai import OpenAI
    if LLM_BASE_URL:
        return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    return OpenAI(api_key=LLM_API_KEY)


class _LLMClient:
    def chat(self, *, system: str, user: str, max_tokens: int, fast: bool = True) -> str:
        """
        Send a single system+user turn and return the response text.

        Args:
            system    : instruction / role prompt
            user      : the actual input content
            max_tokens: upper bound on response length (keep small for classification tasks)
            fast      : True → MODEL_FAST (cheap), False → MODEL_SMART (capable)
        """
        model = MODEL_FAST if fast else MODEL_SMART

        if LLM_PROVIDER == "anthropic":
            return self._anthropic(system, user, max_tokens, model)
        if LLM_PROVIDER == "google":
            return self._google(system, user, max_tokens, model)
        if LLM_PROVIDER == "openai":
            return self._openai(system, user, max_tokens, model)

        raise ValueError(
            f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'. "
            "Set LLM_PROVIDER to: anthropic | google | openai"
        )

    # ── Provider implementations ───────────────────────────────────────────

    def _anthropic(self, system: str, user: str, max_tokens: int, model: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=LLM_API_KEY)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text.strip()

    def _google(self, system: str, user: str, max_tokens: int, model: str) -> str:
        import re
        import time
        from google import genai
        from google.genai import types
        from google.genai.errors import ClientError

        client = genai.Client(api_key=LLM_API_KEY)

        for attempt in range(4):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=user,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        max_output_tokens=max_tokens,
                    ),
                )
                # resp.text can be None for thinking-mode models; fall back to parts
                text = resp.text
                if text is None and resp.candidates:
                    parts = resp.candidates[0].content.parts
                    text = " ".join(p.text for p in parts if getattr(p, "text", None))
                return (text or "").strip()

            except ClientError as e:
                if "RESOURCE_EXHAUSTED" in str(e) and attempt < 3:
                    match = re.search(r"retry in (\d+)", str(e))
                    wait = int(match.group(1)) + 2 if match else 62
                    print(f"  [rate limit] waiting {wait}s before retry...")
                    time.sleep(wait)
                else:
                    raise

    def _openai(self, system: str, user: str, max_tokens: int, model: str) -> str:
        client = _openai_client()
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content.strip()

    # ── Vision (text + images) ─────────────────────────────────────────────

    def vision(
        self,
        *,
        system: str,
        prompt: str,
        images: list[dict],
        max_tokens: int,
        fast: bool = False,
    ) -> str:
        """
        Multi-modal call: text prompt + one or more images.

        Each image is a dict with one of:
            {"type": "url",    "url": "https://..."}
            {"type": "base64", "data": "<b64>", "media_type": "image/png"}

        Args:
            fast: False (default) → MODEL_SMART; True → MODEL_FAST
        """
        model = MODEL_FAST if fast else MODEL_SMART

        if LLM_PROVIDER == "anthropic":
            return self._vision_anthropic(system, prompt, images, max_tokens, model)
        if LLM_PROVIDER == "google":
            return self._vision_google(system, prompt, images, max_tokens, model)
        if LLM_PROVIDER == "openai":
            return self._vision_openai(system, prompt, images, max_tokens, model)

        raise ValueError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'")

    def _vision_anthropic(
        self, system: str, prompt: str, images: list[dict], max_tokens: int, model: str
    ) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=LLM_API_KEY)

        content: list[dict] = []
        for img in images:
            if img["type"] == "url":
                content.append({"type": "image", "source": {"type": "url", "url": img["url"]}})
            else:
                content.append({"type": "image", "source": {
                    "type": "base64",
                    "media_type": img.get("media_type", "image/png"),
                    "data": img["data"],
                }})
        content.append({"type": "text", "text": prompt})

        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        return resp.content[0].text.strip()

    def _vision_google(
        self, system: str, prompt: str, images: list[dict], max_tokens: int, model: str
    ) -> str:
        import base64 as b64mod
        import re
        import time
        import httpx
        from google import genai
        from google.genai import types
        from google.genai.errors import ClientError

        client = genai.Client(api_key=LLM_API_KEY)

        parts: list = []
        for img in images:
            if img["type"] == "url":
                raw = httpx.get(img["url"], timeout=10).content
                mime = "image/jpeg"
            else:
                raw = b64mod.b64decode(img["data"])
                mime = img.get("media_type", "image/png")
            parts.append(types.Part.from_bytes(data=raw, mime_type=mime))
        parts.append(types.Part.from_text(text=prompt))

        for attempt in range(4):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=parts,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        max_output_tokens=max_tokens,
                    ),
                )
                text = resp.text
                if text is None and resp.candidates:
                    ps = resp.candidates[0].content.parts
                    text = " ".join(p.text for p in ps if getattr(p, "text", None))
                return (text or "").strip()
            except ClientError as e:
                if "RESOURCE_EXHAUSTED" in str(e) and attempt < 3:
                    match = re.search(r"retry in (\d+)", str(e))
                    wait = int(match.group(1)) + 2 if match else 62
                    print(f"  [rate limit] waiting {wait}s before retry...")
                    time.sleep(wait)
                else:
                    raise

    def _vision_openai(
        self, system: str, prompt: str, images: list[dict], max_tokens: int, model: str
    ) -> str:
        client = _openai_client()

        img_parts: list[dict] = []
        for img in images:
            if img["type"] == "url":
                img_parts.append({"type": "image_url", "image_url": {"url": img["url"]}})
            else:
                media = img.get("media_type", "image/png")
                img_parts.append({"type": "image_url", "image_url": {
                    "url": f"data:{media};base64,{img['data']}"
                }})
        msg_content = img_parts + [{"type": "text", "text": prompt}]

        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": msg_content},
            ],
        )
        return resp.choices[0].message.content.strip()


# Module-level singleton — import this in processors
llm = _LLMClient()
