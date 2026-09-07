"""Provider-agnostic LLM interface.

The application never imports a vendor SDK directly. It asks this module for
a provider, and every provider exposes the same two capabilities:

* ``complete_json`` - structured output constrained by a JSON schema
* ``complete_text`` - free-form text (used only for prose like draft replies)

A provider is allowed to fail. Callers are expected to degrade to the
deterministic path rather than surface an error, which is why the whole app
runs with ``LLM_PROVIDER=mock`` and no credentials.
"""

from __future__ import annotations

import json
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import LlmError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LlmRequest:
    system: str
    user: str
    #: JSON schema the response must satisfy (structured-output mode).
    schema: dict[str, Any] | None = None
    schema_name: str = "response"
    max_tokens: int = 4096
    temperature: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LlmResponse:
    text: str
    data: dict[str, Any] | None = None
    model: str = "unknown"
    provider: str = "unknown"
    #: Populated when the provider reports usage; purely informational.
    usage: dict[str, Any] = field(default_factory=dict)


class LlmProvider(ABC):
    """Base class every provider implements."""

    name: str = "base"

    def __init__(self, *, max_retries: int = 3, timeout: float = 60.0) -> None:
        self.max_retries = max_retries
        self.timeout = timeout

    @property
    def available(self) -> bool:
        """Whether this provider is configured well enough to be called."""
        return True

    @abstractmethod
    def _invoke(self, request: LlmRequest) -> LlmResponse:
        """Single attempt. Raise on failure; retries are handled for you."""

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Invoke with exponential backoff and jitter.

        Retries are capped and every attempt is logged, so a flaky provider
        shows up in the logs rather than as a mysteriously slow request.
        """
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._invoke(request)
            except Exception as exc:  # noqa: BLE001 - deliberately broad; we retry then degrade
                last_error = exc
                if attempt == self.max_retries:
                    break
                delay = min(2 ** (attempt - 1), 8) + random.uniform(0, 0.4)
                logger.warning(
                    "LLM call failed (provider=%s attempt=%d/%d): %s - retrying in %.1fs",
                    self.name,
                    attempt,
                    self.max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)
        logger.error("LLM call failed permanently (provider=%s): %s", self.name, last_error)
        raise LlmError(
            f"{self.name} provider failed after {self.max_retries} attempts: {last_error}"
        )

    def complete_json(self, request: LlmRequest) -> dict[str, Any]:
        response = self.complete(request)
        if response.data is not None:
            return response.data
        return parse_json_payload(response.text)

    def complete_text(self, request: LlmRequest) -> str:
        return self.complete(request).text


def parse_json_payload(text: str) -> dict[str, Any]:
    """Parse a JSON object out of a model response.

    Tolerates the two things models reliably do wrong: wrapping JSON in a
    markdown fence, and adding a sentence before or after it.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1] if "```" in cleaned[3:] else cleaned[3:]
        if cleaned.lstrip().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    cleaned = cleaned.strip().strip("`").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LlmError("Model response contained no JSON object") from None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LlmError(f"Model returned malformed JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LlmError("Model returned JSON that was not an object")
    return parsed


__all__ = ["LlmProvider", "LlmRequest", "LlmResponse", "parse_json_payload"]
