"""Audit logging service for tracking system operations and domain entity modifications."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ops import AuditEvent


async def record_audit_event(
    db: AsyncSession,
    *,
    actor_id: Optional[uuid.UUID],
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    actor_type: str = "user",
    requisition_id: Optional[uuid.UUID] = None,
    request_id: Optional[str] = None,
    before_version: Optional[int] = None,
    after_version: Optional[int] = None,
    outcome: str = "success",
    safe_metadata: Optional[dict[str, Any]] = None,
) -> AuditEvent:
    """Record an immutable audit event in the database."""
    event = AuditEvent(
        id=uuid.uuid4(),
        occurred_at=datetime.now(timezone.utc),
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        requisition_id=requisition_id,
        request_id=request_id,
        before_version=before_version,
        after_version=after_version,
        outcome=outcome,
        safe_metadata=safe_metadata or {},
    )
    db.add(event)
    await db.flush()
    return event
