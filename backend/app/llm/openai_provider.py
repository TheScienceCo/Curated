"""OpenAI (and OpenAI-compatible) provider.

Structured output uses `response_format: json_schema` with `strict: true`.
Pointing `OPENAI_BASE_URL` at any compatible gateway (vLLM, Together, an
internal proxy) works without code changes - which is the point of keeping
the provider abstraction thin.
"""

from __future__ import annotations

import httpx

from app.core.errors import ConfigurationError, LlmError
from app.llm.base import LlmProvider, LlmRequest, LlmResponse, parse_json_payload

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider(LlmProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str | None,
        model: str = "gpt-4o-mini",
        *,
        base_url: str | None = None,
        max_retries: int = 3,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(max_retries=max_retries, timeout=timeout)
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ConfigurationError("OPENAI_API_KEY is not set")
        return {"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"}

    def _invoke(self, request: LlmRequest) -> LlmResponse:
        payload: dict = {
            "model": self.model,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
        }
        if request.schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name,
                    "schema": request.schema,
                    "strict": False,
                },
            }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/chat/completions", headers=self._headers(), json=payload
            )
        if response.status_code >= 400:
            raise LlmError(f"OpenAI API error {response.status_code}: {response.text[:500]}")

        body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise LlmError("OpenAI response contained no choices")
        text = (choices[0].get("message") or {}).get("content") or ""
        data = parse_json_payload(text) if request.schema else None
        return LlmResponse(
            text=text.strip(),
            data=data,
            model=body.get("model", self.model),
            provider=self.name,
            usage=body.get("usage", {}) or {},
        )


__all__ = ["OpenAIProvider"]
