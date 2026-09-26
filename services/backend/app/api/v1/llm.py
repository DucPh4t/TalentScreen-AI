"""API v1 endpoints for LLM Provider capability probe and Budget Ledger monitoring."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, get_current_context
from app.domain.enums import BudgetScope
from app.services.llm.ledger import get_or_create_active_budget_period
from app.services.llm.probe import run_capability_probe

router = APIRouter(tags=["AI Provider & Budget"])


@router.post("/system/probe-llm", response_model=dict[str, Any])
async def post_probe_llm(
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Run synthetic capability probe to verify model availability, protocol, and usage tracking."""
    return await run_capability_probe()


@router.get("/budget/status", response_model=dict[str, Any])
async def get_budget_status(
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Retrieve current budget period limit, reserved funds, and actual spend."""
    period = await get_or_create_active_budget_period(db, scope=BudgetScope.PILOT)
    limit = float(period.limit_usd)
    reserved = float(period.reserved_usd)
    spent = float(period.spent_usd)
    remaining = max(0.0, limit - spent - reserved)

    return {
        "scope": period.scope.value,
        "limit_usd": limit,
        "reserved_usd": reserved,
        "spent_usd": spent,
        "remaining_available_usd": round(remaining, 6),
        "rate_card_version": period.rate_card_version,
        "period_start": period.period_start.isoformat(),
        "period_end": period.period_end.isoformat(),
    }
