"""Unit tests for configuration validation and security masking."""
import pytest
from app.config import Settings


def test_mock_mode_allows_missing_api_key():
    """Verify that mock mode runs cleanly without any external API key."""
    settings = Settings(
        APP_ENV="sandbox",
        LLM_PROVIDER="mock",
        DEEPSEEK_API_KEY=None,
    )
    assert settings.LLM_PROVIDER == "mock"
    assert settings.DEEPSEEK_API_KEY is None


def test_deepseek_mode_requires_api_key():
    """Verify that deepseek provider requires a non-empty DEEPSEEK_API_KEY."""
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY is required"):
        Settings(
            APP_ENV="sandbox",
            LLM_PROVIDER="deepseek",
            DEEPSEEK_API_KEY="",
        )


def test_pilot_env_requires_valid_pilot_stage():
    """Verify that APP_ENV='pilot' requires PILOT_STAGE to be 'shadow' or 'assisted'."""
    with pytest.raises(ValueError, match="PILOT_STAGE must be 'shadow' or 'assisted'"):
        Settings(
            APP_ENV="pilot",
            PILOT_STAGE=None,
        )

    # Valid pilot configurations
    settings_shadow = Settings(
        APP_ENV="pilot",
        PILOT_STAGE="shadow",
        SECRET_KEY="a" * 64,
        APP_ORIGIN="https://talentscreen.example.edu",
    )
    assert settings_shadow.PILOT_STAGE == "shadow"

    settings_assisted = Settings(
        APP_ENV="pilot",
        PILOT_STAGE="assisted",
        SECRET_KEY="a" * 64,
        APP_ORIGIN="https://talentscreen.example.edu",
    )
    assert settings_assisted.PILOT_STAGE == "assisted"


def test_pilot_rejects_insecure_deployment_configuration():
    secure = dict(_env_file=None, APP_ENV="pilot", PILOT_STAGE="shadow",
                  SECRET_KEY="a" * 64, APP_ORIGIN="https://hr.example.edu")
    with pytest.raises(ValueError, match="non-default SECRET_KEY"):
        Settings(**{**secure, "SECRET_KEY": "dev_secret_key"})
    with pytest.raises(ValueError, match="HTTPS APP_ORIGIN"):
        Settings(**{**secure, "APP_ORIGIN": "http://hr.example.edu"})
    with pytest.raises(ValueError, match="without path"):
        Settings(**{**secure, "APP_ORIGIN": "https://hr.example.edu/api"})
    with pytest.raises(ValueError, match="REQUIRE_SANITIZED_APPROVAL"):
        Settings(**{**secure, "REQUIRE_SANITIZED_APPROVAL": False})


def test_sandbox_env_forbids_pilot_stage():
    """Verify that APP_ENV='sandbox' cannot have PILOT_STAGE set."""
    with pytest.raises(ValueError, match="PILOT_STAGE must be null/None when APP_ENV is 'sandbox'"):
        Settings(
            APP_ENV="sandbox",
            PILOT_STAGE="shadow",
        )


def test_safe_dict_redacts_secrets():
    """Verify that safe_dict() masks sensitive credentials and does not leak secrets."""
    settings = Settings(
        APP_ENV="sandbox",
        SECRET_KEY="super_secret_key_value_1234567890",
        DEEPSEEK_API_KEY="sk-123456789abcdef",
        DATABASE_URL="postgresql+asyncpg://myuser:mypassword@localhost:5432/mydb",
    )
    safe = settings.safe_dict()
    assert safe["SECRET_KEY"] == "[REDACTED]"
    assert safe["DEEPSEEK_API_KEY"] == "[REDACTED]"
    assert "mypassword" not in safe["DATABASE_URL"]
    assert "myuser:****@" in safe["DATABASE_URL"]
