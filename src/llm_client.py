"""
Thin wrapper around the Anthropic Messages API.

Why this exists:
  - Centralizes retry on transient errors (connection / rate-limit).
  - Forces JSON-only responses with a small, robust parser
    (LLMs sometimes wrap JSON in ```json fences even when asked not to).
  - Keeps `pipeline.py` free of provider-specific imports so swapping
    LLMs later is a one-file change.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1024


class LLMError(Exception):
    """Raised when the LLM call cannot be completed or parsed."""


class LLMClient:
    def __init__(self, model: str = DEFAULT_MODEL, max_retries: int = 2):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. "
                "Export it before running: export ANTHROPIC_API_KEY=sk-ant-..."
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_retries = max_retries

    # ------------------------------------------------------------------ #
    # Public
    # ------------------------------------------------------------------ #
    def call_json(self, prompt: str, system: str | None = None) -> dict[str, Any]:
        """Call the LLM and parse the response as JSON."""
        raw = self._call(prompt, system=system)
        return self._parse_json(raw)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #
    def _call(self, prompt: str, system: str | None = None) -> str:
        """Call the LLM with simple exponential backoff for transient errors."""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": self.model,
                    "max_tokens": MAX_TOKENS,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if system:
                    kwargs["system"] = system
                resp = self.client.messages.create(**kwargs)
                # Concatenate text blocks (ignore any tool_use blocks here).
                parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
                return "\n".join(parts).strip()
            except (anthropic.APIConnectionError, anthropic.RateLimitError) as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    "Transient LLM error (attempt %d/%d): %s; retrying in %ds",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                    wait,
                )
                time.sleep(wait)
            except anthropic.APIStatusError as exc:
                # Non-retriable (4xx etc.) — surface immediately.
                raise LLMError(f"LLM API error: {exc}") from exc

        raise LLMError(f"LLM call failed after retries: {last_exc}")

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        """
        Parse the LLM output as JSON. Handles two common annoyances:
          1. ```json ... ``` fences
          2. Leading / trailing prose around the JSON object
        """
        text = raw.strip()

        # Strip code fences if present.
        fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        # First try: direct parse.
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Fallback: pull out the first {...} block.
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError as exc:
                raise LLMError(
                    f"Could not parse JSON from LLM response. Raw output:\n{raw}"
                ) from exc

        raise LLMError(f"No JSON found in LLM response. Raw output:\n{raw}")
