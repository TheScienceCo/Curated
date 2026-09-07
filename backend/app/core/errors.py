"""Application-level exceptions and their HTTP mapping."""

from __future__ import annotations


class AppError(Exception):
    """Base class for errors the API knows how to render."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class LlmError(AppError):
    """Raised when an LLM provider fails after exhausting retries.

    Callers are expected to degrade to the deterministic path rather than
    surface this to the user, so it is mostly informational.
    """

    status_code = 502
    code = "llm_error"


class ConfigurationError(AppError):
    status_code = 500
    code = "configuration_error"


class ExternalServiceError(AppError):
    """Raised when an external service (e.g., Apify) fails."""
    status_code = 502
    code = "external_service_error"
