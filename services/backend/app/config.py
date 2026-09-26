"""Application configuration module for TalentScreen AI.
Strictly typed via Pydantic Settings. Adheres to 02-architecture and 07-operations-deployment.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment & Stage
    APP_ENV: Literal["sandbox", "pilot"] = Field(
        default="sandbox",
        description="Environment mode: 'sandbox' (default) or 'pilot'",
    )
    PILOT_STAGE: Optional[Literal["shadow", "assisted"]] = Field(
        default=None,
        description="Pilot stage (must be None in sandbox, 'shadow' or 'assisted' in pilot)",
    )

    # Server Bind & Origins
    APP_BIND_HOST: str = Field(default="127.0.0.1")
    APP_PORT: int = Field(default=8000)
    APP_ORIGIN: str = Field(
        default="http://localhost:3000",
        description="Single allowed origin for session cookie / CSRF requests",
    )

    # Database URLs
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/talentscreen",
        description="Async PostgreSQL connection URL with asyncpg",
    )
    DATABASE_SYNC_URL: Optional[str] = Field(
        default="postgresql://postgres:postgres@127.0.0.1:5432/talentscreen",
        description="Sync PostgreSQL connection URL for Alembic migrations",
    )

    # Storage
    PRIVATE_STORAGE_ROOT: str = Field(
        default="./private_storage",
        description="Directory path for private blob storage",
    )

    # Security
    SECRET_KEY: str = Field(
        default="dev_secret_key_change_in_production_min_32_characters_needed",
        description="Secret key for signing sessions and tokens",
    )

    # LLM Provider
    LLM_PROVIDER: Literal["mock", "deepseek"] = Field(
        default="mock",
        description="LLM provider: 'mock' (default, safe for local testing) or 'deepseek'",
    )
    DEEPSEEK_BASE_URL: str = Field(default="https://api.deepseek.com")
    DEEPSEEK_MODEL: str = Field(
        default="deepseek-flash",
        description="Model identifier configured by user; verified via probe",
    )
    DEEPSEEK_API_KEY: Optional[str] = Field(
        default=None,
        description="DeepSeek API key (only required when LLM_PROVIDER=deepseek)",
    )

    # Policy & Sanitization
    EXTERNAL_REAL_DATA_POLICY: str = Field(
        default="allowed_deepseek_confirmed_by_owner",
    )
    REQUIRE_SANITIZED_APPROVAL: bool = Field(
        default=True,
        description="Enforce that raw CVs are sanitized and approved by HR before external calls",
    )

    # Embeddings & Retrieval
    EMBEDDING_MODEL: str = Field(default="intfloat/multilingual-e5-base")
    EMBEDDING_DEVICE: str = Field(default="auto")
    EMBEDDING_MODEL_REVISION: str = Field(default="main")
    RAG_MODE: Literal["full_text_baseline", "hybrid"] = Field(
        default="full_text_baseline",
    )

    # Concurrency & Queue limits
    WORKER_CONCURRENCY: int = Field(default=1)
    LLM_MAX_CONCURRENCY: int = Field(default=1)
    JOB_LEASE_SECONDS: int = Field(default=120)
    JOB_HEARTBEAT_SECONDS: int = Field(default=20)

    # Upload limits (10 MiB, 10 pages, 20 files batch)
    UPLOAD_MAX_BYTES: int = Field(default=10485760)
    UPLOAD_MAX_PAGES: int = Field(default=10)
    UPLOAD_BATCH_MAX_FILES: int = Field(default=20)

    # Reliability & Timeouts
    LLM_STAGE_MAX_ATTEMPTS: int = Field(default=2)
    ASSESSMENT_MAX_EXTERNAL_CALLS: int = Field(default=4)
    LLM_READ_TIMEOUT_SECONDS: int = Field(default=90)
    ASSESSMENT_DEADLINE_SECONDS: int = Field(default=900)

    # Budget Caps (USD)
    DEV_EVAL_BUDGET_USD: float = Field(default=10.00)
    PILOT_MONTHLY_BUDGET_USD: float = Field(default=10.00)
    RATE_CARD_VERIFIED_AT: Optional[str] = Field(default=None)

    # Data Retention
    RETENTION_POLICY_ID: str = Field(default="default_sandbox_retention")

    @field_validator(
        "PILOT_STAGE",
        "DEEPSEEK_API_KEY",
        "RATE_CARD_VERIFIED_AT",
        "DATABASE_SYNC_URL",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def storage_path(self) -> Path:
        """Return resolved absolute Path for private storage root."""
        path = Path(self.PRIVATE_STORAGE_ROOT).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @model_validator(mode="after")
    def validate_provider_and_stage(self) -> Settings:
        # Check LLM provider requirements
        if self.LLM_PROVIDER == "deepseek":
            if not self.DEEPSEEK_API_KEY or not self.DEEPSEEK_API_KEY.strip():
                raise ValueError(
                    "DEEPSEEK_API_KEY is required when LLM_PROVIDER is 'deepseek'"
                )

        # Check APP_ENV and PILOT_STAGE
        if self.APP_ENV == "pilot":
            if self.PILOT_STAGE not in ("shadow", "assisted"):
                raise ValueError(
                    "PILOT_STAGE must be 'shadow' or 'assisted' when APP_ENV is 'pilot'"
                )
        elif self.APP_ENV == "sandbox":
            if self.PILOT_STAGE is not None:
                raise ValueError("PILOT_STAGE must be null/None when APP_ENV is 'sandbox'")

        return self

    def safe_dict(self) -> dict[str, Any]:
        """Return a representation of configuration with secrets safely redacted."""
        data = self.model_dump()
        redacted = "[REDACTED]"

        # Redact secrets
        if data.get("DEEPSEEK_API_KEY"):
            data["DEEPSEEK_API_KEY"] = redacted
        if data.get("SECRET_KEY"):
            data["SECRET_KEY"] = redacted

        # Redact database password in URLs if present
        for url_field in ("DATABASE_URL", "DATABASE_SYNC_URL"):
            val = data.get(url_field)
            if val and "@" in val and "://" in val:
                protocol, rest = val.split("://", 1)
                user_pass, host_part = rest.split("@", 1)
                if ":" in user_pass:
                    user, _ = user_pass.split(":", 1)
                    data[url_field] = f"{protocol}://{user}:****@{host_part}"

        return data


# Singleton settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
