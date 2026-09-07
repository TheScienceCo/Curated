"""Anthropic provider.

Uses the Messages API over plain httpx rather than the vendor SDK, so the
backend keeps a single HTTP dependency and the request shape stays visible.
Structured output is obtained with a forced tool call, which is the reliable
way to get schema-conformant JSON out of the API.
"""

from __future__ import annotations

import httpx

from app.core.errors import ConfigurationError, LlmError
from app.llm.base import LlmProvider, LlmRequest, LlmResponse

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider(LlmProvider):
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None,
        model: str = "claude-sonnet-5",
        *,
        max_retries: int = 3,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(max_retries=max_retries, timeout=timeout)
        self.api_key = api_key
        self.model = model

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ConfigurationError("ANTHROPIC_API_KEY is not set")
        return {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

    def _invoke(self, request: LlmRequest) -> LlmResponse:
        payload: dict = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "system": request.system,
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.schema:
            # Forcing a tool call is how the Messages API guarantees the
            # response conforms to a JSON schema.
            payload["tools"] = [
                {
                    "name": request.schema_name,
                    "description": "Return the extracted structured data.",
                    "input_schema": request.schema,
                }
            ]
            payload["tool_choice"] = {"type": "tool", "name": request.schema_name}

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(API_URL, headers=self._headers(), json=payload)
        if response.status_code >= 400:
            raise LlmError(f"Anthropic API error {response.status_code}: {response.text[:500]}")

        body = response.json()
        blocks = body.get("content", [])
        text_parts: list[str] = []
        data: dict | None = None
        for block in blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                candidate = block.get("input")
                if isinstance(candidate, dict):
                    data = candidate

        if request.schema and data is None:
            raise LlmError("Anthropic response did not include the requested tool call")

        return LlmResponse(
            text="\n".join(text_parts).strip(),
            data=data,
            model=body.get("model", self.model),
            provider=self.name,
            usage=body.get("usage", {}) or {},
        )


__all__ = ["AnthropicProvider"]
