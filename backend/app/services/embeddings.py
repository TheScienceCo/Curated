"""Optional semantic embeddings for résumé/job comparison (Phase 6).

Disabled by default. When `EMBEDDINGS_ENABLED=true` and an OpenAI-compatible
key is configured, résumés and job descriptions get dense vectors and the
résumé matcher gains a semantic tiebreaker. When disabled, every function
returns None and the deterministic keyword path is used - which is why the
feature can stay off without degrading anything.

Vectors are stored as JSON arrays today. Moving them to a pgvector column is
a schema change, not an application change, because nothing outside this
module and `resume_match.cosine_similarity` touches the representation.
"""

from __future__ import annotations

import httpx

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
#: Long documents are truncated rather than chunked: résumé variants are short,
#: and chunk-level retrieval is a Phase 6 concern.
MAX_CHARS = 24_000


def embeddings_available(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.embeddings_enabled and settings.openai_api_key)


def embed_text(text: str, settings: Settings | None = None) -> list[float] | None:
    """Embed one document, or return None when embeddings are unavailable."""
    settings = settings or get_settings()
    if not embeddings_available(settings):
        return None
    if not text or not text.strip():
        return None

    base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(
                f"{base_url}/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": DEFAULT_EMBEDDING_MODEL, "input": text[:MAX_CHARS]},
            )
        if response.status_code >= 400:
            logger.warning(
                "Embedding request failed (%s): %s", response.status_code, response.text[:200]
            )
            return None
        data = response.json().get("data") or []
        if not data:
            return None
        vector = data[0].get("embedding")
        return [float(v) for v in vector] if vector else None
    except Exception as exc:  # noqa: BLE001 - embeddings are strictly optional
        logger.warning("Embedding unavailable, continuing without semantic matching: %s", exc)
        return None


__all__ = ["embed_text", "embeddings_available", "DEFAULT_EMBEDDING_MODEL"]
