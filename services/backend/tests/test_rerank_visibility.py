import json
import pytest
from fastapi import HTTPException
from app.db.models import AssessmentRun,User
from app.domain.enums import AccountRole
from app.domain.authorization import AuthenticatedContext
from app.services.assessment.service import get_assessment_run_detail
from tests.test_assessment_agent import agent_context
from tests.test_rerank_kernel import policy

@pytest.mark.asyncio
async def test_summary_is_authorized_private_and_old_rows_null(test_session_factory,agent_context):
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        from app.db.models import SanitizedVersion
        v=await db.get(SanitizedVersion,run.sanitized_version_id)
        user=await db.get(User,v.approved_by)
        admin=AuthenticatedContext(user=user,roles=[AccountRole.ADMIN],session_record=None)
        old=await get_assessment_run_detail(db,run.id,admin)
        assert old.reranking_summary is None
        for mode,applied in [('shadow',False),('rerank',True),('gate_experiment',True)]:
            p=policy(mode);run.snapshot={**run.snapshot,'reranking_policy':p.model_dump(mode='json'),'reranking_policy_hash':p.digest}
            run.rerank_output={'stages':[{'mode':mode,'omitted_limiting_count':2,'unscored_pair_ids':['opaque-pair'],'status':'ok'}],
                'successful_judgments':{'CANARY':{'probabilities':{'unrelated':1},'text':'CANARY_CV'}}}
            await db.commit()
            result=await get_assessment_run_detail(db,run.id,admin)
            assert result.reranking_summary.applied is applied
            assert result.reranking_summary.needs_evidence_review is applied
            assert 'CANARY' not in result.model_dump_json() and 'probabilities' not in result.model_dump_json()
        with pytest.raises(HTTPException) as exc:
            await get_assessment_run_detail(db,run.id,AuthenticatedContext(user=user,roles=[AccountRole.RECRUITER],session_record=None))
        assert exc.value.status_code==403


def test_rerank_trace_exports_allowlisted_aggregates_only():
    from app.services.observability import safe_metadata
    assert safe_metadata({'rerank_mode':'rerank','rerank_elapsed_ms':22,'omitted_count':2,
        'error_code':'JEV_RERANK_FAILED','prompt':'CANARY','probabilities':{'unrelated':1}})=={
            'rerank_mode':'rerank','rerank_elapsed_ms':22,'omitted_count':2,'error_code':'JEV_RERANK_FAILED'}
