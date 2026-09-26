"""Idempotency service to guarantee once-only semantics for mutating endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ops import IdempotencyRecord


async def get_or_start_idempotency(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID,
    method: str,
    route_scope: str,
    key: str,
    request_hash: str,
) -> tuple[Optional[IdempotencyRecord], bool]:
    """Check idempotency key.
    Returns (record, is_cached):
    - If record is completed: returns (record, True) indicating caller should return cached result.
    - If record is processing: raises 409 Conflict.
    - If new: creates record with 'processing' and returns (record, False).
    """
    stmt = select(IdempotencyRecord).where(
        IdempotencyRecord.actor_id == actor_id,
        IdempotencyRecord.method == method.upper(),
        IdempotencyRecord.route_scope == route_scope,
        IdempotencyRecord.key == key,
    ).with_for_update()
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()

    if existing:
        if existing.status == "processing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="REQUEST_IN_PROGRESS: Yêu cầu với Idempotency-Key này đang được xử lý bởi hệ thống.",
            )
        # Completed: return cached response
        return existing, True

    # New idempotency record
    new_record = IdempotencyRecord(
        id=uuid.uuid4(),
        actor_id=actor_id,
        method=method.upper(),
        route_scope=route_scope,
        key=key,
        request_hash=request_hash,
        status="processing",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(new_record)
    await db.flush()
    return new_record, False


async def complete_idempotency(
    db: AsyncSession,
    record: IdempotencyRecord,
    http_status: int,
    resource_ref: dict[str, Any],
) -> None:
    """Mark idempotency record as completed with cached response reference."""
    record.status = "completed"
    record.http_status = http_status
    record.resource_ref = resource_ref
    await db.flush()
