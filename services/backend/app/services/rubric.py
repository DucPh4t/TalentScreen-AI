"""Rubric and Criteria domain services: seed import, editor, validation, and approval."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.requisition import JDVersion, Requisition, RequisitionMembership, RubricCriterion, RubricVersion
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import AccountRole, MembershipRole, RubricStatus, SanitizedVersionStatus

logger = logging.getLogger(__name__)
from app.domain.rubric_policy import RubricValidationError, validate_canonical_rubric
from app.schemas.rubric import (
    CriterionDTO,
    RecommendationPolicyDTO,
    RubricApproveRequest,
    RubricApproveResponse,
    RubricCreateRequest,
    RubricResponse,
    RubricUpdateRequest,
    ScoringAnchorDTO,
    SourceRequirementRefDTO,
)
from app.services.audit import record_audit_event
from app.services.requisition import extract_jd_source_refs


def get_seed_rubric_path() -> Path:
    """Find the path to the canonical seed rubric JSON."""
    candidates = [
        Path("talentscreen-mvp-plan/examples/rubric-backend-python.v1.json"),
        Path("../talentscreen-mvp-plan/examples/rubric-backend-python.v1.json"),
        Path(__file__).parents[4] / "talentscreen-mvp-plan" / "examples" / "rubric-backend-python.v1.json",
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    raise FileNotFoundError("Không tìm thấy file rubric-backend-python.v1.json")


def load_seed_rubric_dict() -> dict[str, Any]:
    """Load and parse canonical rubric seed JSON."""
    path = get_seed_rubric_path()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_content_hash(criteria_data: list[dict[str, Any]], policy_data: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of canonical criteria and policy."""
    canonical = {
        "criteria": sorted(criteria_data, key=lambda c: c.get("id") or c.get("criterion_id", "")),
        "policy": policy_data,
    }
    dumped = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()



async def check_requisition_owner_guard(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> Requisition:
    """Verify requisition exists and caller is OWNER or Admin."""
    stmt_req = select(Requisition).where(Requisition.id == requisition_id).with_for_update()
    req = (await db.execute(stmt_req)).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition không tồn tại.")

    is_admin = AccountRole.ADMIN in ctx.roles
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    mem = (await db.execute(stmt_mem)).scalar_one_or_none()
    is_owner = mem is not None and mem.membership_role == MembershipRole.OWNER

    if not (is_admin or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Owner của Requisition mới có quyền quản lý Rubric.",
        )
    return req


def criterion_model_to_dto(c: RubricCriterion, core_ids: set[str] | None = None) -> CriterionDTO:
    """Convert RubricCriterion DB model to typed CriterionDTO."""
    anchors_dto = []
    raw_anchors = c.anchors or []
    if isinstance(raw_anchors, list):
        for a in raw_anchors:
            anchors_dto.append(
                ScoringAnchorDTO(
                    score=a.get("score", 0),
                    description=a.get("description", ""),
                    qualifying_evidence=a.get("qualifying_evidence", []),
                    not_sufficient=a.get("not_sufficient", []),
                )
            )
    elif isinstance(raw_anchors, dict):
        for score_str, a in sorted(raw_anchors.items(), key=lambda item: int(item[0])):
            anchors_dto.append(
                ScoringAnchorDTO(
                    score=int(score_str),
                    description=a.get("description", "") if isinstance(a, dict) else str(a),
                    qualifying_evidence=a.get("qualifying_evidence", []) if isinstance(a, dict) else [],
                    not_sufficient=a.get("not_sufficient", []) if isinstance(a, dict) else [],
                )
            )

    source_requirements_dto = []
    for ref in (c.jd_evidence_refs or []):
        source_requirements_dto.append(
            SourceRequirementRefDTO(
                requirement_id=ref.get("requirement_id", ""),
                quote=ref.get("quote", ""),
            )
        )

    return CriterionDTO(
        id=c.criterion_id,
        label=c.label_vi,
        description=c.description_vi,
        weight=c.weight,
        core=c.criterion_id in (core_ids or set()),
        source_requirements=source_requirements_dto,
        scoring_anchors=anchors_dto,
        bilingual_terms=c.bilingual_terms,
    )


def rubric_model_to_dto(r: RubricVersion) -> RubricResponse:
    """Convert RubricVersion DB model to RubricResponse DTO."""
    core_ids = set((r.threshold_config or {}).get("core_minimum_scores", {}).keys())
    criteria_dtos = [criterion_model_to_dto(c, core_ids) for c in (r.criteria or [])]
    return RubricResponse(
        id=r.id,
        requisition_id=r.requisition_id,
        jd_version_id=r.jd_version_id,
        version_no=r.version_no,
        status=r.status,
        threshold_config=r.threshold_config or {},
        content_hash=r.content_hash,
        approved_by=r.approved_by,
        approved_at=r.approved_at,
        created_at=r.created_at,
        criteria=criteria_dtos,
    )


async def create_rubric_draft(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    payload: RubricCreateRequest,
    ctx: AuthenticatedContext,
) -> RubricResponse:
    """Create a new Rubric draft via seed import, clone, or manual specification."""
    req = await check_requisition_owner_guard(db, requisition_id, ctx)

    jd_id = payload.jd_version_id or req.current_jd_version_id
    if not jd_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="VALIDATION_ERROR: Requisition chưa có JD version. Hãy tạo JD trước khi tạo Rubric.",
        )

    # Determine next version_no
    stmt_v = select(func.max(RubricVersion.version_no)).where(RubricVersion.requisition_id == requisition_id)
    max_v = (await db.execute(stmt_v)).scalar() or 0
    next_version = max_v + 1

    criteria_to_insert = []
    threshold_config = {}

    if payload.source == "seed":
        seed_data = load_seed_rubric_dict()
        threshold_config = seed_data.get("recommendation_policy", {})
        raw_criteria = seed_data.get("criteria", [])
        jd = (await db.execute(select(JDVersion).where(
            JDVersion.id == jd_id,
            JDVersion.requisition_id == requisition_id,
        ))).scalar_one_or_none()
        if jd is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="JD hiện hành không thuộc đợt tuyển dụng này.")
        jd_requirements = (jd.source_refs or extract_jd_source_refs(jd.source_text)).get("requirements", [])
        try:
            validate_canonical_rubric({"criteria": raw_criteria, "recommendation_policy": threshold_config})
        except RubricValidationError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))

        for c in raw_criteria:
            matching_refs = [ref for ref in jd_requirements if
                ref.get("criterion_id") == c["id"] and
                ref.get("weight") == c["weight"] and
                ref.get("quote") and ref["quote"] in jd.source_text]
            if len(matching_refs) != 1:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"JD cần đúng một yêu cầu nguồn cho {c['id']} với trọng số {c['weight']} trước khi tạo rubric mẫu.",
                )
            criteria_to_insert.append(
                {
                    "criterion_id": c["id"],
                    "label_vi": c["label"],
                    "description_vi": c["description"],
                    "weight": c["weight"],
                    "anchors": c["scoring_anchors"],
                    "jd_evidence_refs": [{"requirement_id": matching_refs[0]["requirement_id"], "quote": matching_refs[0]["quote"]}],
                    "bilingual_terms": c.get("bilingual_terms"),
                }
            )

    elif payload.source == "clone":
        if not payload.clone_from_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="clone_from_id là bắt buộc khi source='clone'.",
            )
        stmt_clone = (
            select(RubricVersion)
            .where(RubricVersion.id == payload.clone_from_id)
            .options(selectinload(RubricVersion.criteria))
        )
        orig = (await db.execute(stmt_clone)).scalar_one_or_none()
        if not orig:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rubric nguồn để clone không tồn tại.")

        threshold_config = orig.threshold_config
        for c in orig.criteria:
            criteria_to_insert.append(
                {
                    "criterion_id": c.criterion_id,
                    "label_vi": c.label_vi,
                    "description_vi": c.description_vi,
                    "weight": c.weight,
                    "anchors": c.anchors,
                    "jd_evidence_refs": c.jd_evidence_refs,
                    "bilingual_terms": c.bilingual_terms,
                }
            )

    elif payload.source == "manual":
        if not payload.rubric:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Payload 'rubric' là bắt buộc khi source='manual'.",
            )
        try:
            validate_canonical_rubric(payload.rubric)
        except RubricValidationError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))

        threshold_config = payload.rubric.get("recommendation_policy") or payload.rubric.get("threshold_config", {})
        threshold_config = dict(threshold_config)
        threshold_config.setdefault(
            "core_minimum_scores",
            {c.get("id") or c.get("criterion_id"): 2 for c in payload.rubric["criteria"] if c.get("core")},
        )
        for c in payload.rubric["criteria"]:
            cid = c.get("id") or c.get("criterion_id")
            label = c.get("label") or c.get("label_vi")
            desc = c.get("description") or c.get("description_vi")
            anchors = c.get("scoring_anchors") or c.get("anchors")
            criteria_to_insert.append(
                {
                    "criterion_id": cid,
                    "label_vi": label,
                    "description_vi": desc,
                    "weight": c["weight"],
                    "anchors": anchors,
                    "jd_evidence_refs": c.get("source_requirements") or c.get("jd_evidence_refs", []),
                    "bilingual_terms": c.get("bilingual_terms"),
                }
            )
    elif payload.source == "ai_draft":
        jd = (await db.execute(select(JDVersion).where(
            JDVersion.id == jd_id,
            JDVersion.requisition_id == requisition_id,
        ))).scalar_one_or_none()
        if jd is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="JD hiện hành không thuộc đợt tuyển dụng này.")
        from app.services.rubric_drafting import draft_jd_rubric
        proposed = await draft_jd_rubric(db, jd, ctx.user.id)
        # A bounded provider call commits its ledger before network I/O. Re-lock
        # and re-check the JD before persisting the draft after that boundary.
        req = await check_requisition_owner_guard(db, requisition_id, ctx)
        await db.refresh(req)
        if req.current_jd_version_id != jd_id:
            raise HTTPException(409, "JD_VERSION_MISMATCH: JD đã thay đổi trong lúc tạo rubric. Hãy thử lại theo bản mới.")
        next_version = ((await db.execute(select(func.max(RubricVersion.version_no)).where(
            RubricVersion.requisition_id == requisition_id))).scalar() or 0) + 1
        raw_criteria = proposed["criteria"]
        threshold_config = proposed["recommendation_policy"]
        for c in raw_criteria:
            criteria_to_insert.append(
                {
                    "criterion_id": c["id"],
                    "label_vi": c["label"],
                    "description_vi": c["description"],
                    "weight": c["weight"],
                    "anchors": c["scoring_anchors"],
                    "jd_evidence_refs": c["source_requirements"],
                    "bilingual_terms": c.get("bilingual_terms"),
                }
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Nguồn rubric không hợp lệ '{payload.source}'. Phải là 'seed', 'clone', 'manual', hoặc 'ai_draft'.",
        )

    # Compute content hash
    content_hash = compute_content_hash(criteria_to_insert, threshold_config)

    # Invariant from 09 backlog: "AI draft chưa được coi approved. Dùng seed không cần provider"
    rubric = RubricVersion(
        id=uuid.uuid4(),
        requisition_id=requisition_id,
        jd_version_id=jd_id,
        version_no=next_version,
        status=RubricStatus.DRAFT,
        threshold_config=threshold_config,
        schema_version="1.0",
        content_hash=content_hash,
        approved_by=None,
        approved_at=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(rubric)
    await db.flush()

    for c_data in criteria_to_insert:
        criterion = RubricCriterion(
            rubric_version_id=rubric.id,
            criterion_id=c_data["criterion_id"],
            label_vi=c_data["label_vi"],
            description_vi=c_data["description_vi"],
            weight=c_data["weight"],
            anchors=c_data["anchors"],
            jd_evidence_refs=c_data["jd_evidence_refs"],
            bilingual_terms=c_data["bilingual_terms"],
        )
        db.add(criterion)
    await db.flush()

    # Log audit event
    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="rubric.create",
        entity_type="rubric_version",
        entity_id=rubric.id,
        requisition_id=requisition_id,
        safe_metadata={"version_no": next_version, "source": payload.source, "content_hash": content_hash},
    )

    # Reload with criteria to return full DTO
    stmt_full = (
        select(RubricVersion)
        .where(RubricVersion.id == rubric.id)
        .options(selectinload(RubricVersion.criteria))
    )
    rubric_loaded = (await db.execute(stmt_full)).scalar_one()
    return rubric_model_to_dto(rubric_loaded)


async def get_rubric_by_id(
    db: AsyncSession,
    rubric_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> RubricResponse:
    """Get canonical rubric version with all criteria and anchors."""
    stmt = (
        select(RubricVersion)
        .where(RubricVersion.id == rubric_id)
        .options(selectinload(RubricVersion.criteria))
    )
    res = await db.execute(stmt)
    rubric = res.scalar_one_or_none()
    if not rubric:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rubric không tồn tại.")

    # Guard: Must be member of requisition or Admin
    is_admin = AccountRole.ADMIN in ctx.roles
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == rubric.requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    mem = (await db.execute(stmt_mem)).scalar_one_or_none()
    if not is_admin and not mem:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập Rubric này.")

    return rubric_model_to_dto(rubric)


async def list_rubrics_for_requisition(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> list[RubricResponse]:
    """List visible rubric versions, including drafts that are not yet current."""
    req = (await db.execute(select(Requisition.id).where(Requisition.id == requisition_id))).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition không tồn tại.")
    if AccountRole.ADMIN not in ctx.roles:
        member = (await db.execute(select(RequisitionMembership).where(
            RequisitionMembership.requisition_id == requisition_id,
            RequisitionMembership.user_id == ctx.user.id,
            RequisitionMembership.active.is_(True),
        ))).scalar_one_or_none()
        if member is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập Rubric của đợt này.")
    versions = (await db.execute(
        select(RubricVersion)
        .where(RubricVersion.requisition_id == requisition_id)
        .options(selectinload(RubricVersion.criteria))
        .order_by(RubricVersion.version_no.desc())
    )).scalars().all()
    return [rubric_model_to_dto(version) for version in versions]


async def update_rubric_draft(
    db: AsyncSession,
    rubric_id: uuid.UUID,
    payload: RubricUpdateRequest,
    ctx: AuthenticatedContext,
    header_if_match: Optional[str] = None,
) -> RubricResponse:
    """Update a draft rubric. Invariant: Only DRAFT rubrics can be edited."""
    stmt = (
        select(RubricVersion)
        .where(RubricVersion.id == rubric_id)
        .options(selectinload(RubricVersion.criteria))
        .with_for_update()
    )
    rubric = (await db.execute(stmt)).scalar_one_or_none()
    if not rubric:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rubric không tồn tại.")

    # Guard: Owner check
    await check_requisition_owner_guard(db, rubric.requisition_id, ctx)

    # Invariant: Only DRAFT rubrics can be edited
    if rubric.status != RubricStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"RUBRIC_IMMUTABLE: Không thể sửa Rubric đã ở trạng thái {rubric.status.value}. Hãy tạo bản sao (clone) hoặc phiên bản mới.",
        )

    # Validate full payload
    try:
        validate_canonical_rubric(payload.rubric)
    except RubricValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))

    raw_criteria = payload.rubric.get("criteria", [])
    threshold_config = payload.rubric.get("recommendation_policy") or payload.rubric.get("threshold_config", {})
    threshold_config = dict(threshold_config)
    threshold_config.setdefault(
        "core_minimum_scores",
        {c.get("id") or c.get("criterion_id"): 2 for c in raw_criteria if c.get("core")},
    )

    # Delete existing criteria
    for old_c in rubric.criteria:
        await db.delete(old_c)
    await db.flush()

    criteria_to_insert = []
    for c in raw_criteria:
        cid = c.get("id") or c.get("criterion_id")
        label = c.get("label") or c.get("label_vi")
        desc = c.get("description") or c.get("description_vi")
        anchors = c.get("scoring_anchors") or c.get("anchors")
        criteria_to_insert.append(
            {
                "criterion_id": cid,
                "label_vi": label,
                "description_vi": desc,
                "weight": c["weight"],
                "anchors": anchors,
                "jd_evidence_refs": c.get("source_requirements") or c.get("jd_evidence_refs", []),
                "bilingual_terms": c.get("bilingual_terms"),
            }
        )
        new_c = RubricCriterion(
            rubric_version_id=rubric.id,
            criterion_id=cid,
            label_vi=label,
            description_vi=desc,
            weight=c["weight"],
            anchors=anchors,
            jd_evidence_refs=c.get("source_requirements") or c.get("jd_evidence_refs", []),
            bilingual_terms=c.get("bilingual_terms"),
        )
        db.add(new_c)

    # Recalculate content hash
    rubric.content_hash = compute_content_hash(criteria_to_insert, threshold_config)
    rubric.threshold_config = threshold_config
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="rubric.update",
        entity_type="rubric_version",
        entity_id=rubric.id,
        requisition_id=rubric.requisition_id,
        safe_metadata={"content_hash": rubric.content_hash},
    )

    stmt_full = (
        select(RubricVersion)
        .where(RubricVersion.id == rubric.id)
        .options(selectinload(RubricVersion.criteria))
    )
    rubric_loaded = (await db.execute(stmt_full)).scalar_one()
    return rubric_model_to_dto(rubric_loaded)


async def approve_rubric(
    db: AsyncSession,
    rubric_id: uuid.UUID,
    payload: RubricApproveRequest,
    ctx: AuthenticatedContext,
    header_if_match: Optional[str] = None,
) -> RubricApproveResponse:
    """Approve a rubric draft, making it the current active rubric for the requisition.
    Transitions previous approved rubric to SUPERSEDED.
    """
    stmt = (
        select(RubricVersion)
        .where(RubricVersion.id == rubric_id)
        .options(selectinload(RubricVersion.criteria))
        .with_for_update()
    )
    rubric = (await db.execute(stmt)).scalar_one_or_none()
    if not rubric:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rubric không tồn tại.")

    # Guard: Owner check
    req = await check_requisition_owner_guard(db, rubric.requisition_id, ctx)

    # Invariant: Reviewer cannot approve
    # (Verified in check_requisition_owner_guard)

    if not payload.acknowledge_thresholds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bắt buộc xác nhận đồng ý với recommendation policy (acknowledge_thresholds=True).",
        )

    # Optimistic locking on requisition
    if req.row_version != payload.expected_requisition_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"VERSION_CONFLICT: Requisition đã bị thay đổi (current: {req.row_version}, expected: {payload.expected_requisition_version}).",
        )

    # Validate JD version consistency
    if payload.expected_jd_version_id != req.current_jd_version_id or rubric.jd_version_id != req.current_jd_version_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="JD_VERSION_MISMATCH: Rubric không khớp với phiên bản JD hiện hành của Requisition.",
        )

    jd = (await db.execute(select(JDVersion).where(JDVersion.id == rubric.jd_version_id))).scalar_one_or_none()
    if jd is None or any(
        not criterion.jd_evidence_refs or any(
            not ref.get("quote") or ref["quote"] not in jd.source_text
            for ref in criterion.jd_evidence_refs
        )
        for criterion in rubric.criteria
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="JD_RUBRIC_SOURCE_MISMATCH: Mỗi tiêu chí phải có trích dẫn nguồn nguyên văn trong JD hiện hành.",
        )

    # Validate canonical criteria
    criteria_dicts = [
        {
            "id": c.criterion_id,
            "weight": c.weight,
            "label": c.label_vi,
            "description": c.description_vi,
            "scoring_anchors": c.anchors,
        }
        for c in rubric.criteria
    ]
    try:
        validate_canonical_rubric({"criteria": criteria_dicts, "recommendation_policy": rubric.threshold_config})
    except RubricValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))

    now = datetime.now(timezone.utc)

    # Supersede previous approved rubric for this requisition
    if req.current_rubric_version_id and req.current_rubric_version_id != rubric.id:
        await db.execute(
            update(RubricVersion)
            .where(RubricVersion.id == req.current_rubric_version_id)
            .values(status=RubricStatus.SUPERSEDED)
        )

    # Approve this rubric
    rubric.status = RubricStatus.APPROVED
    rubric.approved_by = ctx.user.id
    rubric.approved_at = now

    # Update requisition current rubric pointer & increment row_version
    req.current_rubric_version_id = rubric.id
    req.row_version += 1
    req.updated_at = now
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="rubric.approve",
        entity_type="rubric_version",
        entity_id=rubric.id,
        requisition_id=req.id,
        after_version=req.row_version,
        safe_metadata={
            "version_no": rubric.version_no,
            "jd_version_id": str(rubric.jd_version_id),
            "content_hash": rubric.content_hash,
        },
    )

    from app.db.models.candidate import Application
    from app.services.email_draft import invalidate_email_drafts
    affected_ids = list((await db.execute(select(Application.id).where(Application.requisition_id == req.id).order_by(Application.id).with_for_update())).scalars())
    await invalidate_email_drafts(db, affected_ids)

    # Auto-Assessment Trigger: When rubric is approved, auto-trigger assessments
    # including applications assessed against a previous rubric. Historical runs remain immutable.
    try:
        from app.db.models.candidate import Application
        from app.db.models.document import SanitizedVersion
        from app.schemas.assessment import AssessmentRunCreateRequest

        stmt_waiting = (
            select(Application)
            .join(SanitizedVersion, SanitizedVersion.id == Application.current_sanitized_version_id)
            .where(
                Application.requisition_id == req.id,
                Application.status == "active",
                SanitizedVersion.status == SanitizedVersionStatus.APPROVED,
            )
        )
        waiting_apps = (await db.execute(stmt_waiting)).scalars().all()
        for waiting_app in waiting_apps:
            try:
                from app.services.assessment.service import enqueue_assessment_if_needed
                async with db.begin_nested():
                    await enqueue_assessment_if_needed(
                        db=db,
                        application_id=waiting_app.id,
                        payload=AssessmentRunCreateRequest(
                            sanitized_version_id=waiting_app.current_sanitized_version_id,
                            rubric_version_id=rubric.id,
                        ),
                        ctx=ctx,
                    )
                logger.info("Auto-triggered assessment for application %s upon rubric approval", waiting_app.id)
            except Exception as single_err:
                logger.warning("Could not auto-trigger assessment for application %s: %s", waiting_app.id, single_err)
    except Exception as batch_err:
        logger.warning("Auto-trigger assessments on rubric approval skipped: %s", batch_err)

    return RubricApproveResponse(
        rubric=rubric_model_to_dto(rubric),
        requisition_row_version=req.row_version,
    )


async def draft_rubric_from_jd(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> RubricResponse:
    """Auto-synthesize a draft rubric with valid JD evidence citations."""
    return await create_rubric_draft(
        db=db,
        requisition_id=requisition_id,
        payload=RubricCreateRequest(source="ai_draft"),
        ctx=ctx,
    )
