"""API routes for Data Deletion, Retention Policy, and Verification Reports (Task B17)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, get_current_context, require_role
from app.domain.enums import AccountRole
from app.schemas.deletion import (
    DeletionRequestCreate,
    DeletionRequestResponse,
    RetentionPolicyResponse,
    RetentionSweepResponse,
)
from app.services.deletion import (
    apply_deletion_ledger,
    get_deletion_request_detail,
    request_deletion,
    retention_sweep,
)

router = APIRouter(tags=["Data Deletion & Retention"])


@router.post(
    "/deletion-requests",
    response_model=DeletionRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_create_deletion_request(
    payload: DeletionRequestCreate,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Request deletion of an application or candidate.
    - Application scope: Requisition Owner or Account Owner.
    - Candidate scope: Account Owner.
    Immediate tombstone applied and purge worker job enqueued.
    """
    del_req = await request_deletion(db, payload, ctx)
    await db.commit()
    await db.refresh(del_req)
    return del_req


@router.get(
    "/deletion-requests/{id}",
    response_model=DeletionRequestResponse,
)
async def get_deletion_request(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Retrieve deletion request status, inventory, and verification report."""
    return await get_deletion_request_detail(db, id, ctx)


@router.post(
    "/deletion-requests/apply-ledger",
    dependencies=[Depends(require_role(AccountRole.ADMIN))],
)
async def post_apply_deletion_ledger(
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """SEC-11 Compliance: Re-apply deletion ledger after a backup restore drill."""
    result = await apply_deletion_ledger(db)
    await db.commit()
    return result


@router.get(
    "/retention-policy",
    response_model=RetentionPolicyResponse,
)
async def get_retention_policy(
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Get active retention policy configuration, TTL values, and responsible roles."""
    return RetentionPolicyResponse()


@router.post(
    "/retention-sweep",
    response_model=RetentionSweepResponse,
    dependencies=[Depends(require_role(AccountRole.ADMIN))],
)
async def post_retention_sweep(
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Run retention sweep: clear expired temporary files (>24h) and expire backup records (>7d)."""
    result = await retention_sweep(db)
    await db.commit()
    return RetentionSweepResponse(
        swept_temp_files_count=result["swept_temp_files_count"],
        swept_expired_backups_count=result["swept_expired_backups_count"],
        executed_at=result["executed_at"],
    )
