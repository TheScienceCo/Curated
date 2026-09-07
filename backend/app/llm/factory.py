"""Provider selection.

One place decides which provider the app uses, so swapping vendors is an
environment-variable change rather than a code change.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LlmProvider
from app.llm.mock import MockProvider
from app.llm.openai_provider import OpenAIProvider

logger = get_logger(__name__)


def build_provider(settings: Settings) -> LlmProvider:
    kwargs = {"max_retries": settings.llm_max_retries, "timeout": settings.llm_timeout_seconds}
    if settings.llm_provider == "anthropic":
        provider: LlmProvider = AnthropicProvider(
            settings.anthropic_api_key, settings.anthropic_model, **kwargs
        )
    elif settings.llm_provider == "openai":
        provider = OpenAIProvider(
            settings.openai_api_key,
            settings.openai_model,
            base_url=settings.openai_base_url,
            **kwargs,
        )
    else:
        provider = MockProvider(**kwargs)

    if not provider.available and settings.llm_provider != "mock":
        logger.warning(
            "LLM_PROVIDER=%s but no API key is configured; falling back to deterministic "
            "extraction only.",
            settings.llm_provider,
        )
    return provider


@lru_cache
def get_provider() -> LlmProvider:
    return build_provider(get_settings())


__all__ = ["get_provider", "build_provider"]
