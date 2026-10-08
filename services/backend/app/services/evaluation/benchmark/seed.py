"""Synthetic approved fixtures, with explicit origin and no human attestations."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import (Organization,User,UserAccountRole,SessionRecord,Requisition,RequisitionMembership,
    JDVersion,RubricVersion,RubricCriterion,Candidate,Application,Document,SanitizedVersion,SourceSpan)
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import (AccountRole,MembershipRole,UserStatus,RequisitionStatus,RubricStatus,
                             SanitizedVersionStatus,DocumentSafetyStatus)
from app.domain.security import hash_password
from app.services.audit import record_audit_event
from .contracts import DatasetInputs,RunSelection
from .dataset import canonical_case
from .isolation import IsolationContext,assert_isolated_database

@dataclass(frozen=True)
class SeededCase:
    case_id: str
    application_id: uuid.UUID
    document_id: uuid.UUID
    sanitized_version_id: uuid.UUID
    rubric_version_id: uuid.UUID
    ctx: AuthenticatedContext

async def seed_cases(db: AsyncSession,inputs: DatasetInputs,selection: RunSelection,
                     context: IsolationContext) -> dict[str,SeededCase]:
    await assert_isolated_database(db,context)
    now=datetime.now(timezone.utc)
    org=Organization(id=uuid.uuid4(),name='Synthetic AI Benchmark '+str(context.experiment_id))
    db.add(org)
    owner=User(id=uuid.uuid4(),login_name='benchmark_'+uuid.uuid4().hex,display_name='Synthetic fixture actor',
               password_hash=hash_password(secrets.token_hex(32)),status=UserStatus.ACTIVE)
    db.add(owner)
    await db.flush()
    db.add(UserAccountRole(user_id=owner.id,role=AccountRole.ADMIN))
    session=SessionRecord(id=uuid.uuid4(),user_id=owner.id,token_hash=secrets.token_bytes(32),
                         csrf_hash=secrets.token_bytes(32),user_session_generation=1,expires_at=now+timedelta(hours=2))
    db.add(session)
    await db.flush()
    ctx=AuthenticatedContext(owner,[AccountRole.ADMIN],session)
    role_objects={}
    for role_id in {c.role_family for c in inputs.cases if c.case_id in selection.case_ids}:
        role=inputs.roles[role_id]
        req=Requisition(id=uuid.uuid4(),organization_id=org.id,title=role.title,status=RequisitionStatus.OPEN,row_version=1)
        db.add(req)
        await db.flush()
        db.add(RequisitionMembership(requisition_id=req.id,user_id=owner.id,membership_role=MembershipRole.OWNER))
        jd=JDVersion(id=uuid.uuid4(),requisition_id=req.id,version_no=1,source_text=role.jd_text,
            text_hash=hashlib.sha256(role.jd_text.encode()).hexdigest(),created_by=owner.id,
            egress_reviewed_by=owner.id,egress_reviewed_at=now,source_refs={'origin':'synthetic'})
        db.add(jd)
        await db.flush()
        content='|'.join(c.model_dump_json() for c in role.criteria)
        rubric=RubricVersion(id=uuid.uuid4(),requisition_id=req.id,jd_version_id=jd.id,version_no=1,
            status=RubricStatus.APPROVED,content_hash=hashlib.sha256(content.encode()).hexdigest(),
            threshold_config=role.policy,approved_by=owner.id,approved_at=now)
        db.add(rubric)
        await db.flush()
        for c in role.criteria:
            db.add(RubricCriterion(rubric_version_id=rubric.id,criterion_id=c.id,label_vi=c.label,
                description_vi=c.description,weight=c.weight,
                anchors={str(a.score):a.model_dump(exclude={'score'}) for a in c.scoring_anchors},
                jd_evidence_refs=[r.model_dump() for r in c.source_requirements],bilingual_terms=c.bilingual_terms))
        req.current_jd_version_id=jd.id
        req.current_rubric_version_id=rubric.id
        role_objects[role_id]=(req,rubric)
    seeded={}
    for case in inputs.cases:
        if case.case_id not in selection.case_ids: continue
        req,rubric=role_objects[case.role_family]
        candidate=Candidate(id=uuid.uuid4(),organization_id=org.id,public_label='BENCH-'+uuid.uuid4().hex)
        db.add(candidate)
        await db.flush()
        application=Application(id=uuid.uuid4(),requisition_id=req.id,candidate_id=candidate.id,generation=1,row_version=1)
        db.add(application)
        await db.flush()
        version_id,canonical,spans=canonical_case(case)
        doc=Document(id=uuid.uuid4(),application_id=application.id,version_no=1,original_name_private='synthetic.txt',
            mime_verified='text/plain',byte_size=len(case.cv_text.encode()),sha256=hashlib.sha256(case.cv_text.encode()).hexdigest(),
            blob_key='synthetic/'+case.case_id,ingestion_status='parsed',safety_status=DocumentSafetyStatus.PASSED,created_by=owner.id,
            parser_manifest={'origin':'synthetic_canonical_fixture'})
        db.add(doc)
        await db.flush()
        version=SanitizedVersion(id=version_id,application_id=application.id,document_id=doc.id,version_no=1,
            status=SanitizedVersionStatus.APPROVED,canonical_text=canonical,sha256=hashlib.sha256(canonical.encode()).hexdigest(),
            approved_by=owner.id,approved_at=now,quality_flags={'origin':'synthetic_design_expected','human_attestation':False})
        db.add(version)
        await db.flush()
        for s in spans:
            db.add(SourceSpan(span_id=s.span_id,full_hash=s.full_hash,sanitized_version_id=version.id,start_cp=s.start_cp,
                end_cp=s.end_cp,text=s.text,page_number=s.page_number,section_label=s.section_label,language=s.language))
        application.current_document_id=doc.id
        application.current_sanitized_version_id=version.id
        await record_audit_event(db,actor_id=owner.id,action='benchmark.seed',entity_type='application',entity_id=application.id,
            requisition_id=req.id,safe_metadata={'origin':'synthetic_design_expected','human_attestation':False,
                'case_id':case.case_id,'manifest_hash':inputs.manifest_hash,'experiment_id':str(context.experiment_id)})
        seeded[case.case_id]=SeededCase(case.case_id,application.id,doc.id,version.id,rubric.id,ctx)
    await db.flush()
    return seeded
