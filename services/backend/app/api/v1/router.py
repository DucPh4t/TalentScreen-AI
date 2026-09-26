"""API v1 router for TalentScreen AI."""
from datetime import datetime, timezone
from fastapi import APIRouter
from app.config import get_settings
from app.api.v1.auth import router as auth_router
from app.api.v1.intake import router as intake_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.requisitions import router as requisitions_router
from app.api.v1.rubrics import router as rubrics_router
from app.api.v1.sanitization import router as sanitization_router

router = APIRouter(prefix="/v1")
router.include_router(auth_router)
router.include_router(requisitions_router)
router.include_router(rubrics_router)
router.include_router(intake_router)
router.include_router(jobs_router)
router.include_router(sanitization_router)



@router.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint. Does not make paid external calls or reveal secrets."""
    settings = get_settings()
    return {
        "status": "healthy",
        "app_env": settings.APP_ENV,
        "pilot_stage": settings.PILOT_STAGE,
        "llm_provider": settings.LLM_PROVIDER,
        "rag_mode": settings.RAG_MODE,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/config/diagnostic", tags=["System"])
async def diagnostic_config():
    """Diagnostic configuration endpoint returning redacted settings."""
    settings = get_settings()
    return {
        "status": "ok",
        "config": settings.safe_dict(),
    }
