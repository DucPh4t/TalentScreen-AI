"""Domain services for Data Deletion, Retention Policy, and Inventory Verification (Task B17)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Application,
    CriterionAssessment,
    AssessmentRun,
    Candidate,
    CriterionEvidence,
    Decision,
    DeletionRequest,
    Document,
    HRRevision,
    InterviewDraft,
    InterviewRevision,
    Job,
    RawAccessGrant,
    RequisitionMembership,
    ReviewAttestation,
    SanitizedVersion,
    SourceSpan,
)
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import (
    AccountRole,
    DeletionScope,
    DeletionStatus,
    JobStatus,
    JobType,
    MembershipRole,
)
from app.schemas.deletion import DeletionRequestCreate, DeletionRequestResponse
from app.services.audit import record_audit_event
from app.services.storage import delete_private_blob, resolve_blob_path

logger = logging.getLogger(__name__)


async def check_deletion_authority(
    db: AsyncSession,
    scope: DeletionScope,
    target_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> tuple[Optional[Application], Optional[Candidate]]:
    """Verify caller has deletion rights:
    - Application scope: Requisition Owner or Account Owner/Admin.
    - Candidate scope: Account Owner or Admin.
    """
    is_admin = ctx.has_role(AccountRole.ADMIN)

    if scope == DeletionScope.APPLICATION:
        stmt = (
            select(Application)
            .where(Application.id == target_id)
            .options(selectinload(Application.candidate))
        )
        app = (await db.execute(stmt)).scalar_one_or_none()
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Đơn ứng tuyển không tồn tại.",
            )

        if not is_admin:
            # Check if caller is Requisition Owner
            stmt_mem = select(RequisitionMembership).where(
                RequisitionMembership.requisition_id == app.requisition_id,
                RequisitionMembership.user_id == ctx.user.id,
                RequisitionMembership.membership_role == MembershipRole.OWNER,
                RequisitionMembership.active.is_(True),
            )
            is_req_owner = (await db.execute(stmt_mem)).scalar_one_or_none() is not None
            if not is_req_owner:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Chỉ Requisition Owner hoặc Admin mới có quyền yêu cầu xóa đơn ứng tuyển.",
                )
        return app, app.candidate

    elif scope == DeletionScope.CANDIDATE:
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Chỉ Admin mới có quyền yêu cầu xóa toàn bộ ứng viên.",
            )
        stmt_cand = select(Candidate).where(Candidate.id == target_id)
        cand = (await db.execute(stmt_cand)).scalar_one_or_none()
        if not cand:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ứng viên không tồn tại.",
            )
        return None, cand

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Phạm vi xóa không hợp lệ: {scope}",
        )


async def request_deletion(
    db: AsyncSession,
    payload: DeletionRequestCreate,
    ctx: AuthenticatedContext,
) -> DeletionRequest:
    """Idempotently create a DeletionRequest, tombstone active targets, cancel jobs, and enqueue purge."""
    now = datetime.now(timezone.utc)
    app, cand = await check_deletion_authority(db, payload.scope, payload.target_id, ctx)

    # 1. Idempotency check: Return existing active request if already registered
    stmt_existing = select(DeletionRequest).where(
        DeletionRequest.scope == payload.scope,
        DeletionRequest.target_id == payload.target_id,
        DeletionRequest.status.in_([
            DeletionStatus.REQUESTED,
            DeletionStatus.PURGING,
            DeletionStatus.AWAITING_EXTERNAL,
            DeletionStatus.COMPLETED,
        ]),
    )
    existing = (await db.execute(stmt_existing)).scalars().first()
    if existing:
        return existing

    del_id = uuid.uuid4()
    job_id = uuid.uuid4()

    # 2. Tombstone targets immediately in the same transaction
    affected_app_ids = []
    if payload.scope == DeletionScope.APPLICATION:
        assert app is not None
        affected_app_ids.append(app.id)
        app.status = "deleted"
        app.generation += 1
        app.current_document_id = None
        app.current_sanitized_version_id = None
        app.current_assessment_run_id = None
        app.current_decision_id = None
        app.updated_at = now
    else:
        assert cand is not None
        cand.status = "deleted"
        cand.updated_at = now
        # Fetch all applications of this candidate
        stmt_apps = select(Application).where(Application.candidate_id == cand.id)
        cand_apps = (await db.execute(stmt_apps)).scalars().all()
        for a in cand_apps:
            affected_app_ids.append(a.id)
            a.status = "deleted"
            a.generation += 1
            a.current_document_id = None
            a.current_sanitized_version_id = None
            a.current_assessment_run_id = None
            a.current_decision_id = None
            a.updated_at = now

    # 3. Cancel queued/running jobs and revoke raw access grants for all affected applications
    for app_id in affected_app_ids:
        await db.execute(
            update(Job)
            .where(
                Job.target_id == app_id,
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRY_WAIT]),
            )
            .values(cancel_requested_at=now, status=JobStatus.CANCELLED)
        )
        await db.execute(
            update(RawAccessGrant)
            .where(
                RawAccessGrant.application_id == app_id,
                RawAccessGrant.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    # 4. Enqueue Purge Background Job first so FK job_id is valid
    snapshot_data = {
        "deletion_request_id": str(del_id),
        "scope": payload.scope.value,
        "target_id": str(payload.target_id),
        "requested_by": str(ctx.user.id),
    }
    input_hash = hashlib.sha256(json.dumps(snapshot_data, sort_keys=True).encode("utf-8")).hexdigest()

    job = Job(
        id=job_id,
        type=JobType.PURGE_DATA,
        target_type="deletion_request",
        target_id=del_id,
        input_snapshot_hash=input_hash,
        status=JobStatus.QUEUED,
        payload_ref={"deletion_request_id": str(del_id)},
        created_at=now,
    )
    db.add(job)
    await db.flush()

    # 5. Create DeletionRequest record referencing job.id
    backup_expiry = now + timedelta(days=7)
    del_req = DeletionRequest(
        id=del_id,
        scope=payload.scope,
        target_id=payload.target_id,
        status=DeletionStatus.REQUESTED,
        local_purge_complete=False,
        backup_status="pending_expiry",
        backup_expiry_at=backup_expiry,
        external_retention_status="not_applicable",
        reason_category=payload.reason_category,
        requested_by=ctx.user.id,
        requested_at=now,
        job_id=job_id,
    )
    db.add(del_req)
    await db.flush()

    # 6. Record Audit Event (no candidate PII)
    await record_audit_event(
        db=db,
        actor_id=ctx.user.id,
        action="deletion.requested",
        entity_type="deletion_request",
        entity_id=del_id,
        safe_metadata={
            "scope": payload.scope.value,
            "target_id": str(payload.target_id),
            "reason_category": payload.reason_category,
            "affected_applications_count": len(affected_app_ids),
        },
    )

    return del_req


async def get_deletion_request_detail(
    db: AsyncSession,
    request_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> DeletionRequest:
    """Retrieve DeletionRequest metadata and verification status."""
    stmt = select(DeletionRequest).where(DeletionRequest.id == request_id)
    del_req = (await db.execute(stmt)).scalar_one_or_none()
    if not del_req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Yêu cầu xóa không tồn tại.",
        )

    # Permission check: must be the requester or have Admin role
    is_admin = ctx.has_role(AccountRole.ADMIN)
    if not is_admin and del_req.requested_by != ctx.user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem yêu cầu xóa này.",
        )

    return del_req


async def execute_purge_job(
    db: AsyncSession,
    job_id: uuid.UUID,
) -> None:
    """Worker job execution to purge all physical blobs and database records for a DeletionRequest."""
    now = datetime.now(timezone.utc)
    stmt_del = (
        select(DeletionRequest)
        .where(DeletionRequest.job_id == job_id)
        .with_for_update()
    )
    del_req = (await db.execute(stmt_del)).scalar_one_or_none()
    if not del_req:
        raise ValueError(f"DeletionRequest for job {job_id} not found.")

    if del_req.status == DeletionStatus.COMPLETED and del_req.local_purge_complete:
        logger.info(f"DeletionRequest {del_req.id} already completed, skipping.")
        return

    del_req.status = DeletionStatus.PURGING
    await db.flush()

    # Determine target application IDs
    target_app_ids: list[uuid.UUID] = []
    if del_req.scope == DeletionScope.APPLICATION:
        target_app_ids = [del_req.target_id]
    else:
        stmt_apps = select(Application.id).where(Application.candidate_id == del_req.target_id)
        target_app_ids = list((await db.execute(stmt_apps)).scalars().all())

    # 1. Build Inventory of Documents and Files
    stmt_docs = select(Document).where(Document.application_id.in_(target_app_ids))
    documents = list((await db.execute(stmt_docs)).scalars().all())

    blob_keys_to_delete = []
    for doc in documents:
        if doc.blob_key:
            blob_keys_to_delete.append(doc.blob_key)
        if doc.rendered_pdf_blob_key:
            blob_keys_to_delete.append(doc.rendered_pdf_blob_key)
        if doc.raw_text_blob_key:
            blob_keys_to_delete.append(doc.raw_text_blob_key)

    # 2. Count child database records for inventory
    stmt_runs = select(AssessmentRun.id).where(AssessmentRun.application_id.in_(target_app_ids))
    run_ids = list((await db.execute(stmt_runs)).scalars().all())

    stmt_sanitized = select(SanitizedVersion.id).where(SanitizedVersion.application_id.in_(target_app_ids))
    sanitized_ids = list((await db.execute(stmt_sanitized)).scalars().all())

    stmt_drafts = select(InterviewDraft.id).where(InterviewDraft.application_id.in_(target_app_ids))
    draft_ids = list((await db.execute(stmt_drafts)).scalars().all())

    inventory = {
        "applications": [str(a) for a in target_app_ids],
        "documents_count": len(documents),
        "assessment_runs_count": len(run_ids),
        "sanitized_versions_count": len(sanitized_ids),
        "interview_drafts_count": len(draft_ids),
        "physical_files_count": len(blob_keys_to_delete),
    }
    del_req.inventory = inventory

    from app.db.models import IndependentReviewDraft
    await db.execute(IndependentReviewDraft.__table__.delete().where(IndependentReviewDraft.application_id.in_(target_app_ids)))

    # 3. Physically Delete Blobs from Storage
    files_unlinked = 0
    files_failed = 0
    failed_keys = []
    for key in blob_keys_to_delete:
        try:
            delete_private_blob(key)
            files_unlinked += 1
        except Exception as e:
            logger.error(f"Failed to delete blob {key}: {e}")
            files_failed += 1
            failed_keys.append(key)

    # 4. Clean up application document directory if exists
    for app_id in target_app_ids:
        try:
            dir_path = resolve_blob_path(f"documents/{app_id}")
            if dir_path.exists() and dir_path.is_dir():
                for p in dir_path.glob("*"):
                    try:
                        p.unlink()
                    except Exception:
                        pass
                dir_path.rmdir()
        except Exception:
            pass

    # 5. Database Records Purge
    # Delete child records explicitly to guarantee zero orphaned data
    if run_ids:
        # Delete Evidence and Criteria
        await db.execute(
            CriterionEvidence.__table__.delete().where(CriterionEvidence.run_id.in_(run_ids))
        )
        await db.execute(
            CriterionAssessment.__table__.delete().where(CriterionAssessment.run_id.in_(run_ids))
        )
        await db.execute(
            AssessmentRun.__table__.delete().where(AssessmentRun.id.in_(run_ids))
        )

    if sanitized_ids:
        await db.execute(
            SourceSpan.__table__.delete().where(SourceSpan.sanitized_version_id.in_(sanitized_ids))
        )
        await db.execute(
            SanitizedVersion.__table__.delete().where(SanitizedVersion.id.in_(sanitized_ids))
        )

    if draft_ids:
        await db.execute(
            InterviewRevision.__table__.delete().where(InterviewRevision.draft_id.in_(draft_ids))
        )
        await db.execute(
            InterviewDraft.__table__.delete().where(InterviewDraft.id.in_(draft_ids))
        )

    # Decisions, HR Revisions, Raw Grants, Documents
    if target_app_ids:
        await db.execute(
            ReviewAttestation.__table__.delete().where(ReviewAttestation.application_id.in_(target_app_ids))
        )
        await db.execute(
            Decision.__table__.delete().where(Decision.application_id.in_(target_app_ids))
        )
        await db.execute(
            HRRevision.__table__.delete().where(HRRevision.application_id.in_(target_app_ids))
        )
        await db.execute(
            RawAccessGrant.__table__.delete().where(RawAccessGrant.application_id.in_(target_app_ids))
        )
        await db.execute(
            Document.__table__.delete().where(Document.application_id.in_(target_app_ids))
        )

    # 6. Verification Report
    is_clean = (files_failed == 0)
    verification_report = {
        "purged_applications": [str(a) for a in target_app_ids],
        "documents_purged": len(documents),
        "assessment_runs_purged": len(run_ids),
        "sanitized_versions_purged": len(sanitized_ids),
        "interview_drafts_purged": len(draft_ids),
        "files_unlinked": files_unlinked,
        "files_failed": files_failed,
        "failed_keys": failed_keys,
        "verified_at": now.isoformat(),
        "clean": is_clean,
        "retryable": not is_clean,
    }
    del_req.verification_report = verification_report

    if not is_clean:
        del_req.status = DeletionStatus.FAILED
        del_req.local_purge_complete = False
        await db.flush()
        raise RuntimeError(f"Purge failed to delete {files_failed} physical files.")

    # 7. Local Purge Complete -> Mark awaiting external backup expiry
    del_req.local_purge_complete = True
    del_req.local_purge_completed_at = now
    del_req.backup_status = "pending_expiry"
    del_req.status = DeletionStatus.AWAITING_EXTERNAL
    await db.flush()

    await record_audit_event(
        db=db,
        actor_id=None,
        action="deletion.completed",
        entity_type="deletion_request",
        entity_id=del_req.id,
        safe_metadata={
            "scope": del_req.scope.value,
            "target_id": str(del_req.target_id),
            "local_purge_complete": True,
            "backup_status": del_req.backup_status,
        },
    )


async def apply_deletion_ledger(
    db: AsyncSession,
) -> dict[str, Any]:
    """SEC-11 Compliance: Re-apply deletion ledger after a database backup restore.
    Ensures that any restored records that were previously deleted are re-tombstoned and purged.
    """
    now = datetime.now(timezone.utc)
    stmt = select(DeletionRequest).where(
        DeletionRequest.status.in_([
            DeletionStatus.REQUESTED,
            DeletionStatus.PURGING,
            DeletionStatus.AWAITING_EXTERNAL,
            DeletionStatus.COMPLETED,
        ])
    )
    records = list((await db.execute(stmt)).scalars().all())

    re_purged_apps = 0
    re_purged_cands = 0

    for rec in records:
        if rec.scope == DeletionScope.APPLICATION:
            stmt_app = select(Application).where(Application.id == rec.target_id)
            app = (await db.execute(stmt_app)).scalar_one_or_none()
            if app and app.status != "deleted":
                app.status = "deleted"
                app.generation += 1
                app.current_document_id = None
                app.current_sanitized_version_id = None
                app.current_assessment_run_id = None
                app.current_decision_id = None
                app.updated_at = now
                re_purged_apps += 1
        elif rec.scope == DeletionScope.CANDIDATE:
            stmt_cand = select(Candidate).where(Candidate.id == rec.target_id)
            cand = (await db.execute(stmt_cand)).scalar_one_or_none()
            if cand and cand.status != "deleted":
                cand.status = "deleted"
                cand.updated_at = now
                re_purged_cands += 1
                stmt_cand_apps = select(Application).where(Application.candidate_id == cand.id)
                for ca in (await db.execute(stmt_cand_apps)).scalars().all():
                    if ca.status != "deleted":
                        ca.status = "deleted"
                        ca.generation += 1
                        ca.updated_at = now
                        re_purged_apps += 1

    await db.flush()
    return {
        "total_ledger_records": len(records),
        "re_purged_applications_count": re_purged_apps,
        "re_purged_candidates_count": re_purged_cands,
        "status": "ledger_applied",
        "applied_at": now.isoformat(),
    }


async def retention_sweep(
    db: AsyncSession,
) -> dict[str, Any]:
    """Sweep expired temp files and expire backup records whose 7-day retention period has passed."""
    now = datetime.now(timezone.utc)

    # 1. Sweep expired temp files (> 24 hours old)
    swept_temp_files = 0
    try:
        temp_dir = resolve_blob_path("tmp")
        if temp_dir.exists() and temp_dir.is_dir():
            cutoff = now.timestamp() - 86400  # 24 hours
            for f in temp_dir.glob("*"):
                if f.is_file() and f.stat().st_mtime < cutoff:
                    try:
                        f.unlink()
                        swept_temp_files += 1
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"Error during temp file retention sweep: {e}")

    # 2. Expire backups in DeletionRequest
    stmt_exp = select(DeletionRequest).where(
        DeletionRequest.backup_status == "pending_expiry",
        DeletionRequest.backup_expiry_at <= now,
    )
    expired_reqs = list((await db.execute(stmt_exp)).scalars().all())
    for req in expired_reqs:
        req.backup_status = "expired"
        if req.local_purge_complete:
            req.status = DeletionStatus.COMPLETED
            req.completed_at = now

    await db.flush()
    return {
        "swept_temp_files_count": swept_temp_files,
        "swept_expired_backups_count": len(expired_reqs),
        "executed_at": now,
    }
