"""Tests for health and diagnostic endpoints."""
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_root_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "app_env" in data
        assert "timestamp_utc" in data


@pytest.mark.asyncio
async def test_api_v1_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["llm_provider"] in ("mock", "deepseek")


@pytest.mark.asyncio
async def test_diagnostic_config_does_not_leak_secrets():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/config/diagnostic")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        config = data["config"]
        if config.get("SECRET_KEY"):
            assert config["SECRET_KEY"] == "[REDACTED]"
        if config.get("DEEPSEEK_API_KEY"):
            assert config["DEEPSEEK_API_KEY"] == "[REDACTED]"
