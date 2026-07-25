"""Application configuration and secure secret handling.

Settings are loaded from environment variables (and an optional local `.env`
file) via pydantic-settings. The Anthropic API key is never hard-coded and never
logged — see `redacted_api_key` for the only representation that is safe to print.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, populated from the environment.

    A real secret (the API key) is stored as a `SecretStr`, so it does not leak
    when a Settings instance is repr'd, logged, or serialized by accident.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Environment variables are matched case-insensitively.
        case_sensitive=False,
    )

    # --- Secrets -----------------------------------------------------------
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        description="Anthropic API key. Prefer setting ANTHROPIC_API_KEY in the "
        "environment; an `ant auth login` profile is also picked up by the SDK.",
    )

    # --- Model / generation settings --------------------------------------
    model: str = Field(
        default="claude-opus-5",
        description="Claude model ID used for requirement generation.",
    )
    max_tokens: int = Field(default=8000, ge=256, le=64000)
    effort: str = Field(
        default="medium",
        description="Reasoning effort: low | medium | high | xhigh | max.",
    )
    request_timeout_seconds: float = Field(default=120.0, gt=0)

    # --- Service settings --------------------------------------------------
    app_name: str = "AI Requirements Assistant"
    log_level: str = Field(default="INFO")
    log_json: bool = Field(
        default=False,
        description="Emit logs as JSON lines instead of human-readable text.",
    )

    @property
    def has_api_key(self) -> bool:
        """True if an explicit API key was configured via the environment.

        Note: the SDK can also authenticate through an `ant auth login` profile
        with no key set, so a False here does not guarantee that calls will fail.
        """
        return self.anthropic_api_key is not None

    @property
    def redacted_api_key(self) -> str:
        """A safe-to-log representation of the API key (last 4 chars only)."""
        if self.anthropic_api_key is None:
            return "<unset>"
        raw = self.anthropic_api_key.get_secret_value()
        if len(raw) <= 4:
            return "****"
        return f"****{raw[-4:]}"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (one load per process)."""
    return Settings()
