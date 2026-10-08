"""Application configuration module for TalentScreen AI.
Strictly typed via Pydantic Settings. Adheres to 02-architecture and 07-operations-deployment.
"""
from __future__ import annotations

import math
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import urlsplit
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
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
        default="http://localhost:2004",
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

    # Jev is an optional, separate decision model. It remains disabled until
    # the institution approves this processor and verifies its rate card.
    JEV_MODE: Literal["off", "shadow"] = Field(default="off")
    JEV_API_KEY: Optional[str] = Field(default=None)
    JEV_BASE_URL: str = Field(default="https://openrouter.ai/api/v1/systemone")
    JEV_MODEL: str = Field(default="typesafe/jev-1.13")
    JEV_DATA_PROCESSING_APPROVED: bool = Field(default=False)
    JEV_INPUT_PRICE_PER_MILLION_USD: Optional[float] = Field(default=None)
    JEV_RATE_CARD_VERIFIED_AT: Optional[str] = Field(default=None)

    # Developer observability: no candidate content is exported.
    LANGSMITH_TRACING: bool = Field(default=False)
    LANGSMITH_API_KEY: Optional[str] = Field(default=None, repr=False)
    LANGSMITH_PROJECT: str = Field(default="talentscreen-dev", min_length=1, max_length=100)
    LANGSMITH_ENDPOINT: str = Field(default="https://api.smith.langchain.com")

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
    EMBEDDING_MODEL_REVISION: str = Field(
        default="d128750597153bb5987e10b1c3493a34e5a4502a",
        description="Immutable model repository commit used for reproducible retrieval",
    )
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
    ASSESSMENT_MAX_EXTERNAL_CALLS: int = Field(default=4, ge=1, le=4)
    LLM_READ_TIMEOUT_SECONDS: int = Field(default=90)
    ASSESSMENT_DEADLINE_SECONDS: int = Field(default=900)

    # Budget Caps (USD)
    DEV_EVAL_BUDGET_USD: float = Field(default=10.00, gt=0)
    PILOT_MONTHLY_BUDGET_USD: float = Field(default=10.00, gt=0)
    REQUISITION_LLM_BUDGET_USD: Optional[Decimal] = Field(default=None, gt=0)
    RATE_CARD_VERIFIED_AT: Optional[str] = Field(default=None)

    # Data Retention
    RETENTION_POLICY_ID: str = Field(default="default_sandbox_retention")

    @field_validator(
        "PILOT_STAGE",
        "DEEPSEEK_API_KEY",
        "LANGSMITH_API_KEY",
        "JEV_API_KEY",
        "JEV_INPUT_PRICE_PER_MILLION_USD",
        "REQUISITION_LLM_BUDGET_USD",
        "RATE_CARD_VERIFIED_AT",
        "JEV_RATE_CARD_VERIFIED_AT",
        "DATABASE_SYNC_URL",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("DEV_EVAL_BUDGET_USD", "PILOT_MONTHLY_BUDGET_USD")
    @classmethod
    def require_finite_budget_caps(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Budget caps must be finite values")
        return value

    @field_validator("REQUISITION_LLM_BUDGET_USD")
    @classmethod
    def require_finite_requisition_budget(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("REQUISITION_LLM_BUDGET_USD must be finite")
        return value

    @field_validator("JEV_BASE_URL")
    @classmethod
    def require_https_jev_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"api.typesafe.ai", "openrouter.ai"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (parsed.hostname == "api.typesafe.ai" and parsed.path != "/v1/systemone")
            or (parsed.hostname == "openrouter.ai" and parsed.path != "/api/v1/systemone")
        ):
            raise ValueError("JEV_BASE_URL must be the HTTPS TypeSafe or OpenRouter System One endpoint without credentials/query/fragment")
        return value.rstrip("/")

    @field_validator("LANGSMITH_ENDPOINT")
    @classmethod
    def require_langsmith_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.hostname not in {"api.smith.langchain.com", "eu.api.smith.langchain.com"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/") or parsed.port not in (None, 443)):
            raise ValueError("LANGSMITH_ENDPOINT must be the HTTPS US or EU LangSmith API origin")
        return value.rstrip("/")

    @property
    def storage_path(self) -> Path:
        """Return resolved absolute Path for private storage root."""
        path = Path(self.PRIVATE_STORAGE_ROOT).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def requisition_budget_limit_usd(self) -> Decimal:
        """Return the per-requisition ceiling, inheriting the dev cap in sandbox."""
        if self.REQUISITION_LLM_BUDGET_USD is not None:
            return self.REQUISITION_LLM_BUDGET_USD
        return Decimal(str(self.DEV_EVAL_BUDGET_USD))

    @model_validator(mode="after")
    def validate_provider_and_stage(self) -> Settings:
        if self.LANGSMITH_TRACING and not self.LANGSMITH_API_KEY:
            raise ValueError("LANGSMITH_API_KEY is required when LANGSMITH_TRACING=true")
        # Check LLM provider requirements
        if self.LLM_PROVIDER == "deepseek":
            if not self.DEEPSEEK_API_KEY or not self.DEEPSEEK_API_KEY.strip():
                raise ValueError(
                    "DEEPSEEK_API_KEY is required when LLM_PROVIDER is 'deepseek'"
                )

        if self.JEV_MODE == "shadow":
            if not self.JEV_API_KEY or not self.JEV_API_KEY.strip():
                raise ValueError("JEV_API_KEY is required when JEV_MODE is 'shadow'")
            if not self.JEV_DATA_PROCESSING_APPROVED:
                raise ValueError("JEV_DATA_PROCESSING_APPROVED must be true before enabling JEV shadow processing")
            is_openrouter = urlsplit(self.JEV_BASE_URL).hostname == "openrouter.ai"
            model_pattern = r"typesafe/jev-\d+\.\d+" if is_openrouter else r"jev-\d+\.\d+(?:\.\d+)?"
            if not re.fullmatch(model_pattern, self.JEV_MODEL):
                raise ValueError("JEV_MODEL must be a pinned Jev model ID compatible with the configured System One provider; rolling aliases are not permitted")
            if self.JEV_INPUT_PRICE_PER_MILLION_USD is None or self.JEV_INPUT_PRICE_PER_MILLION_USD <= 0:
                raise ValueError("A verified positive JEV_INPUT_PRICE_PER_MILLION_USD is required")
            if not self.JEV_RATE_CARD_VERIFIED_AT:
                raise ValueError("JEV_RATE_CARD_VERIFIED_AT is required before enabling JEV shadow processing")

        # Check APP_ENV and PILOT_STAGE
        if self.APP_ENV == "pilot":
            if self.PILOT_STAGE not in ("shadow", "assisted"):
                raise ValueError(
                    "PILOT_STAGE must be 'shadow' or 'assisted' when APP_ENV is 'pilot'"
                )
            if self.REQUISITION_LLM_BUDGET_USD is None:
                raise ValueError(
                    "REQUISITION_LLM_BUDGET_USD must be explicitly configured outside sandbox"
                )
            if len(self.SECRET_KEY) < 32 or self.SECRET_KEY.startswith("dev_secret_key"):
                raise ValueError("Pilot requires a non-default SECRET_KEY of at least 32 characters")
            origin = urlsplit(self.APP_ORIGIN)
            if origin.scheme != "https" or not origin.hostname or origin.username or origin.password:
                raise ValueError("Pilot requires an HTTPS APP_ORIGIN")
            if origin.path not in ("", "/") or origin.query or origin.fragment:
                raise ValueError("APP_ORIGIN must be an origin, without path, query or fragment")
            if not self.REQUIRE_SANITIZED_APPROVAL:
                raise ValueError("Pilot requires REQUIRE_SANITIZED_APPROVAL=true")
        elif self.APP_ENV == "sandbox":
            if self.PILOT_STAGE is not None:
                raise ValueError("PILOT_STAGE must be null/None when APP_ENV is 'sandbox'")

        return self

    def safe_dict(self) -> dict[str, Any]:
        """Return a representation of configuration with secrets safely redacted."""
        data = self.model_dump()
        redacted = "[REDACTED]"

        # Redact secrets
        for secret_field in ("DEEPSEEK_API_KEY", "JEV_API_KEY", "LANGSMITH_API_KEY"):
            if data.get(secret_field):
                data[secret_field] = redacted
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
