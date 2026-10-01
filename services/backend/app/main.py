"""Main FastAPI application factory for TalentScreen AI."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.api.v1.router import router as api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context: initialize storage and local prerequisites."""
    settings = get_settings()
    # Ensure storage root directory exists
    _ = settings.storage_path
    yield
    # Cleanup if needed on shutdown


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="TalentScreen AI Backend",
        description="Modular Monolith Backend for CV Screening and Evidence Verification",
        version="0.1.0",
        docs_url="/docs" if settings.APP_ENV == "sandbox" else None,
        redoc_url="/redoc" if settings.APP_ENV == "sandbox" else None,
        openapi_url="/openapi.json" if settings.APP_ENV == "sandbox" else None,
        lifespan=lifespan,
    )

    # CORS Middleware: strictly bound to APP_ORIGIN (e.g. Next.js at localhost:2004)
    # Does NOT use wildcard '*' with credentials
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.APP_ORIGIN],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Include API Routers
    app.include_router(api_v1_router, prefix="/api")

    @app.get("/health", tags=["Health"])
    async def root_health():
        return {
            "status": "healthy",
            "app_env": settings.APP_ENV,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }

    return app


app = create_app()
