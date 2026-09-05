"""
Thin client for Groq's chat-completions API(OpenAI-compatible schema).

This is the "real AI agent" seam: services/assistant_service.py and
rag/rag_service.py both call `chat()` to turn grounded facts (a real model
prediction + real SHAP features + real retrieved manual passages) into a
natural-language answer, instead of the old string-template composition.

Configure with the GROQ_API_KEY environment variable (see config.py). If no
key is set, `is_configured()` is False and callers fall back to their
existing templated behavior -- the app still runs fully offline with no key.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 60


def is_configured() -> bool:
    return config.LLM_ENABLED


def chat(system_prompt: str, user_prompt: str, *, max_tokens: int = 1200, temperature: float = 0.2) -> str | None:
    """Call Groq's chat completions endpoint. Returns the response text, or None
    if the LLM isn't configured or the call fails for any reason -- callers must
    treat None as "fall back to the deterministic/templated path", never as an
    error to surface to the user. This keeps the LLM a pure enhancement layer;
    the app's grounded facts (predictions, SHAP, retrieved chunks) are never
    themselves produced by the LLM, only phrased by it.
    """
    if not is_configured():
        return None

    try:
        resp = requests.post(
            f"{config.GROQ_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        print("\n[GROQ ERROR]")
        print(type(exc).__name__)
        print(str(exc))
        print("[END GROQ ERROR]\n")
        return None
