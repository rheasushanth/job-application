"""LLM provider abstraction.

The application must work with or without an API key. With a key, the LLM does
the language-shaped work: structuring a resume, reading a job description,
writing explanations. Without one, every call site falls back to a deterministic
implementation and the response records `source="fallback"` so the UI can say so
rather than pretending.

The LLM is never asked for a match percentage.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


@dataclass
class LLMResult:
    ok: bool
    data: Any = None
    text: str = ""
    source: str = "fallback"  # "llm" | "fallback"
    error: str | None = None


def llm_available() -> bool:
    return settings.llm_enabled


def provider_name() -> str:
    return f"anthropic:{settings.llm_model}" if settings.llm_enabled else "none (offline fallbacks)"


async def complete(
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.0,
    prefill: str | None = None,
) -> LLMResult:
    """Single-turn completion. Returns ok=False instead of raising."""
    if not settings.llm_enabled:
        return LLMResult(ok=False, error="no_api_key")

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    if prefill:
        messages.append({"role": "assistant", "content": prefill})

    body: dict[str, Any] = {
        "model": settings.llm_model,
        "max_tokens": max_tokens or settings.llm_max_output_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        body["system"] = system

    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            resp = await client.post(ANTHROPIC_URL, json=body, headers=headers)
        if resp.status_code != 200:
            logger.warning("LLM call failed: %s %s", resp.status_code, resp.text[:300])
            return LLMResult(ok=False, error=f"http_{resp.status_code}")
        payload = resp.json()
        parts = [b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text"]
        text = "".join(parts)
        if prefill:
            text = prefill + text
        return LLMResult(ok=True, text=text, source="llm")
    except Exception as exc:  # network, timeout, parse
        logger.warning("LLM call errored: %s", exc)
        return LLMResult(ok=False, error=str(exc)[:200])


async def complete_json(
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int | None = None,
) -> LLMResult:
    """Completion constrained to a JSON object via assistant prefill."""
    result = await complete(
        prompt,
        system=system,
        max_tokens=max_tokens,
        temperature=0.0,
        prefill="{",
    )
    if not result.ok:
        return result
    data = _extract_json(result.text)
    if data is None:
        return LLMResult(ok=False, text=result.text, error="unparseable_json")
    return LLMResult(ok=True, data=data, text=result.text, source="llm")


def _extract_json(text: str) -> Any | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Recover the outermost balanced object if the model trailed off.
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : idx + 1])
                except json.JSONDecodeError:
                    return None
    return None
