"""The no-credentials provider.

`MockProvider` deliberately returns nothing useful: it reports itself as
unavailable, so the extraction pipeline uses the deterministic rule-based
path alone. That is what makes `LLM_PROVIDER=mock` (the default) a working
configuration rather than a broken one - the whole MVP, including the
acceptance test in the README, runs without an API key.
"""

from __future__ import annotations

from app.core.errors import LlmError
from app.llm.base import LlmProvider, LlmRequest, LlmResponse


class MockProvider(LlmProvider):
    name = "mock"

    @property
    def available(self) -> bool:
        return False

    def _invoke(self, request: LlmRequest) -> LlmResponse:
        raise LlmError(
            "The mock provider does not call a model. Set LLM_PROVIDER=anthropic or "
            "LLM_PROVIDER=openai (with the matching API key) to enable LLM enrichment."
        )


__all__ = ["MockProvider"]
