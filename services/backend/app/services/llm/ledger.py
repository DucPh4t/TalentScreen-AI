"""Budget ledger, reservation, and settlement engine.
Invariants:
  1. Atomic reservation with pessimistic locking (FOR UPDATE) to prevent race conditions.
  2. Unknown provider outcomes are NOT treated as free (held as outcome_unknown).
  3. Strict enforcement of period expenditure caps.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.ops import BudgetPeriod, BudgetReservation
from app.domain.enums import BudgetScope
from app.services.llm.cost import RATE_CARD_VERSION
from app.services.llm.exceptions import BudgetExceededError

logger = logging.getLogger(__name__)

async def get_or_create_active_budget_period(
    db: AsyncSession,
    scope: BudgetScope = BudgetScope.PILOT,
    for_update: bool = False,
) -> BudgetPeriod:
    """Retrieve the current active budget period or initialize one if absent."""
    now = datetime.now(timezone.utc)

    stmt = (
        select(BudgetPeriod)
        .where(
            BudgetPeriod.scope == scope,
            BudgetPeriod.period_start <= now,
            BudgetPeriod.period_end > now,
        )
    )
    if for_update:
        stmt = stmt.with_for_update()

    res = await db.execute(stmt)
    period = res.scalar_one_or_none()

    if not period:
        # Create a 30-day budget period
        settings = get_settings()
        configured_limit = (
            settings.DEV_EVAL_BUDGET_USD
            if scope == BudgetScope.DEVELOPMENT
            else settings.PILOT_MONTHLY_BUDGET_USD
        )
        p_start = now
        p_end = now + timedelta(days=30)
        period = BudgetPeriod(
            id=uuid.uuid4(),
            scope=scope,
            period_start=p_start,
            period_end=p_end,
            limit_usd=configured_limit,
            reserved_usd=0.0,
            spent_usd=0.0,
            rate_card_version=RATE_CARD_VERSION,
            created_at=now,
            updated_at=now,
        )
        db.add(period)
        await db.flush()

    return period


async def reserve_budget(
    db: AsyncSession,
    job_id: uuid.UUID,
    amount_usd: Decimal,
    scope: BudgetScope = BudgetScope.PILOT,
) -> BudgetReservation:
    """Atomically reserve funds in the active budget period before initiating an external LLM request."""
    now = datetime.now(timezone.utc)
    period = await get_or_create_active_budget_period(db, scope=scope, for_update=True)

    current_reserved = Decimal(str(period.reserved_usd))
    current_spent = Decimal(str(period.spent_usd))
    limit = Decimal(str(period.limit_usd))

    projected_total = current_spent + current_reserved + amount_usd
    if projected_total > limit:
        raise BudgetExceededError(
            f"BUDGET_LIMIT_EXCEEDED: Cannot reserve ${amount_usd:.4f}. Current spent: ${current_spent:.4f}, "
            f"reserved: ${current_reserved:.4f}, limit: ${limit:.4f}"
        )

    period.reserved_usd = float(current_reserved + amount_usd)
    period.updated_at = now

    reservation = BudgetReservation(
        id=uuid.uuid4(),
        budget_period_id=period.id,
        job_id=job_id,
        amount_usd=float(amount_usd),
        settled_usd=0.0,
        status="reserved",
        created_at=now,
        updated_at=now,
    )
    db.add(reservation)
    await db.flush()

    return reservation


async def settle_budget(
    db: AsyncSession,
    reservation_id: uuid.UUID,
    actual_cost_usd: Optional[Decimal] = None,
    outcome_unknown: bool = False,
) -> BudgetReservation:
    """Reconcile reserved budget after request completes.
    Invariant: If outcome_unknown=True, funds remain held and are NOT treated as free.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(BudgetReservation)
        .where(BudgetReservation.id == reservation_id)
        .with_for_update()
    )
    reservation = (await db.execute(stmt)).scalar_one_or_none()
    if not reservation:
        raise ValueError(f"Reservation {reservation_id} not found.")

    # Lock associated period
    stmt_p = select(BudgetPeriod).where(BudgetPeriod.id == reservation.budget_period_id).with_for_update()
    period = (await db.execute(stmt_p)).scalar_one()

    res_amount = Decimal(str(reservation.amount_usd))
    current_reserved = Decimal(str(period.reserved_usd))
    current_spent = Decimal(str(period.spent_usd))

    if outcome_unknown:
        # Invariant: Do NOT release reservation; flag as outcome_unknown
        reservation.status = "outcome_unknown"
        reservation.updated_at = now
        logger.warning(
            f"Reservation {reservation_id} marked OUTCOME_UNKNOWN. "
            f"Held amount ${res_amount:.4f} retained in budget."
        )
    elif actual_cost_usd is not None:
        cost = Decimal(str(actual_cost_usd))
        period.reserved_usd = float(max(Decimal(0), current_reserved - res_amount))
        period.spent_usd = float(current_spent + cost)
        period.updated_at = now

        reservation.settled_usd = float(cost)
        reservation.status = "settled" if cost > 0 else "released"
        reservation.updated_at = now
    else:
        # Release completely (e.g. preflight check failed before network call)
        period.reserved_usd = float(max(Decimal(0), current_reserved - res_amount))
        period.updated_at = now

        reservation.settled_usd = 0.0
        reservation.status = "released"
        reservation.updated_at = now

    await db.flush()
    return reservation
