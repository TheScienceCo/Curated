"""Application settings, loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LlmProviderName = Literal["mock", "anthropic", "openai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "local"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    seed_on_startup: bool = True

    # Database ------------------------------------------------------------
    database_url: str | None = None
    postgres_user: str = "jia"
    postgres_password: str = "jia_local_password"
    postgres_db: str = "jia"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # LLM -----------------------------------------------------------------
    llm_provider: LlmProviderName = "mock"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None

    embeddings_enabled: bool = False

    # External services ---------------------------------------------------
    apify_api_token: str | None = None

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _normalize_provider(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip().lower()
            return cleaned or "mock"
        return value

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

__all__ = ["Settings", "get_settings", "settings", "LlmProviderName", "Field"]
