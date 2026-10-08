"""Behavior regressions for the approved screening/interview workflow B."""
import uuid
import pytest
from sqlalchemy import select
from app.db.models import Application, Requisition, RubricCriterion, InterviewScorecard
from tests.test_workflow_ux import context, client

async def criteria(factory, ctx):
    async with factory() as db:
        return list((await db.execute(select(RubricCriterion.criterion_id).where(RubricCriterion.rubric_version_id == ctx['rubric_id']))).scalars())

async def screen(api, ctx, ids, outcome='advance', previous=None):
    app = (await api.get(f"/api/v1/applications/{ctx['app_id']}")).json()
    return await api.post(f"/api/v1/applications/{ctx['app_id']}/screening-decision", json={
        'effective_result': {'kind': 'assessment_run', 'id': app['current_assessment_run_id']},
        'reviewed_criterion_ids': ids, 'acknowledged': True, 'outcome': outcome,
        'reason': 'Đã đối chiếu các năng lực trong CV và các tiêu chí của vị trí.',
        'expected_previous_decision_id': previous, 'expected_rubric_version_id': str(ctx['rubric_id'])})

def plan(ids, ctx, version=0):
    return {'expected_version': version, 'label': 'Trao đổi chuyên môn', 'focus_criterion_ids': ids[:2],
            'interviewer_ids': [str(ctx['owner'].id), str(ctx['reviewer'].id)],
            'starts_at': None, 'duration_minutes': 45, 'channel': 'online', 'meeting_location': '',
            'source_hash': None}

def card(ids, outcome='assessed'):
    return [{'criterion_id': cid, 'outcome': outcome if i < 2 else 'not_observed',
             'score': 3 if i < 2 and outcome == 'assessed' else None,
             'answer_summary': 'Ứng viên giải thích rõ cách xử lý và ví dụ đã thực hiện.' if i < 2 else '',
             'interviewer_note': ''} for i, cid in enumerate(ids)]

@pytest.mark.asyncio
async def test_atomic_screening_override_supersede_and_waiting_state(test_session_factory):
    ctx = await context(test_session_factory, assessment=True); ids = await criteria(test_session_factory, ctx)
    async with client(ctx) as api:
        from app.db.models import AssessmentRun
        from app.domain.enums import Recommendation
        async with test_session_factory() as db:
            application = await db.get(Application,ctx['app_id']); run = await db.get(AssessmentRun,application.current_assessment_run_id)
            run.recommendation = Recommendation.NEEDS_CLARIFICATION; await db.commit()
        first = await screen(api, ctx, ids, 'request_information')
        assert first.status_code == 201, first.text
        progress = (await api.get(f"/api/v1/applications/{ctx['app_id']}/progress")).json()
        assert progress['stage'] == 'waiting_information'
        second = await screen(api, ctx, ids, previous=first.json()['id'])
        assert second.status_code == 201, second.text
        assert second.json()['supersedes_decision_id'] == first.json()['id']
        assert second.json()['override_reason'] == second.json()['reason']
        assert (await api.get(f"/api/v1/applications/{ctx['app_id']}/progress")).json()['stage'] == 'awaiting_interview'
        lost_update = await screen(api, ctx, ids, 'not_advance', previous=first.json()['id'])
        assert lost_update.status_code == 409
        async with test_session_factory() as db:
            application = await db.get(Application, ctx['app_id']); application.generation += 1; await db.commit()
        assert (await api.get(f"/api/v1/applications/{ctx['app_id']}/progress")).json()['stage'] != 'awaiting_interview'

@pytest.mark.asyncio
async def test_review_progress_restores_and_invalidates_on_source_change(test_session_factory):
    ctx = await context(test_session_factory, assessment=True); ids = await criteria(test_session_factory, ctx)
    route = f"/api/v1/applications/{ctx['app_id']}/review-progress"
    async with client(ctx) as api:
        initial = await api.get(route); assert initial.status_code == 200
        state = initial.json()
        payload = {'source_hash': state['source_hash'], 'expected_version': state['row_version'], 'reviewed_criterion_ids': ids[:2]}
        saved = await api.put(route, json=payload); assert saved.status_code == 200, saved.text
        assert (await api.get(route)).json()['reviewed_criterion_ids'] == ids[:2]
        assert (await api.put(route, json=payload)).status_code == 409
        async with test_session_factory() as db:
            application = await db.get(Application, ctx['app_id']); application.generation += 1; await db.commit()
        assert (await api.get(route)).json()['reviewed_criterion_ids'] == []
        assert (await api.put(route, json={**payload, 'expected_version': saved.json()['row_version']})).status_code == 409

@pytest.mark.asyncio
async def test_round_focus_blind_owner_correction_and_conclusion(test_session_factory):
    ctx = await context(test_session_factory, assessment=True); ids = await criteria(test_session_factory, ctx)
    route = f"/api/v1/applications/{ctx['app_id']}/interview-rounds/1"
    async with client(ctx) as owner, client(ctx, 'r') as reviewer:
        initial = await owner.get(route); assert initial.status_code == 200
        payload = {**plan(ids, ctx), 'source_hash': initial.json()['source_hash']}
        saved = await owner.put(route, json=payload); assert saved.status_code == 200, saved.text
        assert (await owner.put(route, json=payload)).status_code == 409
        assert (await reviewer.put(route, json={**payload, 'expected_version': 1})).status_code == 403
        score_route = f"/api/v1/applications/{ctx['app_id']}/interview-scorecards"
        request = {'round_no': 1, 'expected_version': 0, 'criteria': card(ids), 'submit': True}
        reviewed = await reviewer.put(score_route, json=request); assert reviewed.status_code == 200, reviewed.text
        hidden = await owner.get(score_route); assert hidden.json() == []
        own = await owner.put(score_route, json=request); assert own.status_code == 200, own.text
        assert own.json()['status'] == 'finalized'
        visible = (await owner.get(score_route)).json(); assert len(visible) == 2
        assert (await screen(owner, ctx, ids)).status_code == 201
        conclusion = await owner.post(route + '/conclusions', json={'expected_version': saved.json()['row_version'], 'outcome': 'propose_hire', 'reason': 'Hai người phỏng vấn đã đối chiếu đầy đủ năng lực trọng tâm.'})
        assert conclusion.status_code == 201, conclusion.text
        assert len(conclusion.json()['conclusions']) == 1
        assert len(conclusion.json()['conclusions'][0]['scorecards']) == 2
        assert (await owner.get(f"/api/v1/applications/{ctx['app_id']}/progress")).json()['stage'] == 'interview_completed'
        queue = (await owner.get(f"/api/v1/requisitions/{ctx['req_id']}/review-queue")).json()
        assert next(row for row in queue if row['application_id'] == str(ctx['app_id']))['workflow_stage'] == 'interview_completed'
        assert (await reviewer.post(route + '/conclusions', json={'expected_version': 2, 'outcome': 'not_advance', 'reason': 'Đánh giá năng lực không phù hợp với yêu cầu vị trí.'})).status_code == 403
        amended = await owner.post(f"/api/v1/interview-scorecards/{own.json()['id']}/amend", json={
            'expected_version': own.json()['row_version'], 'criteria': [{**e, 'score': 2 if e['score'] is not None else None} for e in card(ids)],
            'change_reason': 'Sửa mức điểm theo ghi nhận gốc, giữ nguyên lượt phỏng vấn.'})
        assert amended.status_code == 200, amended.text
        assert len(amended.json()['amendment_history']) == 1
        assert amended.json()['amendment_history'][0]['criteria'][0]['score'] == 3
        assert (await owner.get(route)).json()['conclusion_stale'] is True
        async with test_session_factory() as db:
            application = await db.get(Application, ctx['app_id']); application.generation += 1; await db.commit()
        assert (await owner.get(route)).json()['is_stale'] is True
        assert (await owner.post(route+'/conclusions', json={'expected_version': 2, 'outcome': 'propose_hire', 'reason': 'Đánh giá lại đầy đủ năng lực đã quan sát sau phỏng vấn.'})).status_code == 409

@pytest.mark.asyncio
async def test_unobserved_focus_requires_explanation_before_submit(test_session_factory):
    ctx = await context(test_session_factory, assessment=True); ids = await criteria(test_session_factory, ctx)
    route = f"/api/v1/applications/{ctx['app_id']}/interview-rounds/1"
    async with client(ctx) as api:
        state = (await api.get(route)).json()
        assert (await api.put(route, json={**plan(ids, ctx), 'source_hash': state['source_hash']})).status_code == 200
        rows = card(ids); rows[1] = {**rows[1], 'outcome': 'not_observed', 'score': None, 'answer_summary': ''}
        result = await api.put(f"/api/v1/applications/{ctx['app_id']}/interview-scorecards", json={'round_no': 1, 'expected_version': 0, 'criteria': rows, 'submit': True})
        assert result.status_code == 422
        rows[1]['answer_summary'] = 'Chưa hỏi tiêu chí này vì buổi phỏng vấn bị gián đoạn.'
        result = await api.put(f"/api/v1/applications/{ctx['app_id']}/interview-scorecards", json={'round_no': 1, 'expected_version': 0, 'criteria': rows, 'submit': True})
        assert result.status_code == 200, result.text
        assert result.json()['criteria'][1]['score'] is None

@pytest.mark.asyncio
async def test_interview_questions_validate_sources_and_jd_freshness(test_session_factory):
    from app.db.models import InterviewDraft
    ctx = await context(test_session_factory, assessment=True)
    async with test_session_factory() as db:
        application = await db.get(Application, ctx['app_id']); req = await db.get(Requisition, ctx['req_id'])
        draft = InterviewDraft(application_id=ctx['app_id'], job_id=uuid.uuid4(), created_by=ctx['owner'].id,
            status='succeeded', source_hash='f'*64, source_snapshot={'document_id': str(ctx['doc_id']), 'sanitized_version_id': str(ctx['sanitized_id']),
                'application_generation': 1, 'rubric_version_id': str(ctx['rubric_id']), 'jd_version_id': str(req.current_jd_version_id),
                'effective_result_kind':'assessment_run','effective_result_id':str(application.current_assessment_run_id)}, questions_payload={'followups': []})
        db.add(draft); await db.commit(); draft_id = draft.id
    async with client(ctx) as api:
        bad = await api.post(f'/api/v1/interview-drafts/{draft_id}/revisions', json={'change_reason': 'Chỉnh câu hỏi theo năng lực cần kiểm chứng.',
            'followups': [{'criterion_id': 'python_backend', 'question_vi': 'Bạn đã xây dựng dịch vụ Python nào?', 'purpose_vi': 'Kiểm chứng kinh nghiệm thực tế.', 'source_span_ids': ['spn_unknown'], 'answer_indicators': ['Giải thích được ví dụ cụ thể.']}]})
        assert bad.status_code == 422
        async with test_session_factory() as db:
            req = await db.get(Requisition, ctx['req_id']); req.current_jd_version_id = uuid.uuid4(); await db.commit()
        detail = await api.get(f'/api/v1/interview-drafts/{draft_id}')
        assert detail.json()['is_stale'] is True
        assert (await api.post(f'/api/v1/interview-drafts/{draft_id}/revisions', json={'change_reason': 'Chỉnh câu hỏi theo tiêu chí năng lực hiện tại.', 'followups': []})).status_code == 409

@pytest.mark.asyncio
async def test_invitation_needs_real_schedule_and_current_round(test_session_factory):
    ctx = await context(test_session_factory, assessment=True); ids = await criteria(test_session_factory, ctx)
    route = f"/api/v1/applications/{ctx['app_id']}"
    async with client(ctx) as api:
        assert (await screen(api, ctx, ids)).status_code == 201
        draft = (await api.post(route+'/email-draft/generate')).json()
        update = {'subject': draft['subject'], 'body': draft['body'], 'status': 'approved', 'draft_id': draft['id'], 'expected_version': draft['version_no'], 'acknowledged_content': True}
        result = await api.put(route+'/email-draft', json=update)
        assert result.status_code == 409
        assert 'EMAIL_SCHEDULE_REQUIRED' in result.text
        state = (await api.get(route+'/interview-rounds/1')).json()
        result = await api.put(route+'/interview-rounds/1', json={**plan(ids, ctx), 'source_hash': state['source_hash'], 'starts_at': '2026-10-22T03:00:00+00:00', 'meeting_location': 'https://meet.example.com/synthetic'})
        assert result.status_code == 200
        draft = (await api.post(route+'/email-draft/generate')).json()
        assert '22/10/2026' in draft['body']
        assert '[Ngày' not in draft['body']
        assert (await api.put(route+'/email-draft', json={**update, 'body': draft['body'], 'draft_id': draft['id'], 'expected_version': draft['version_no']})).status_code == 200

@pytest.mark.asyncio
async def test_workflow_b_migration_round_trip_isolated(test_engine):
    import subprocess, sys
    from sqlalchemy import inspect
    def columns(connection):
        inspector = inspect(connection)
        return {'tables': inspector.get_table_names(), 'card': [c['name'] for c in inspector.get_columns('interview_scorecards')]}
    async with test_engine.connect() as connection:
        before = await connection.run_sync(columns)
    assert 'review_progress' in before['tables'] and 'amendment_history' in before['card']
    result = subprocess.run([sys.executable, '-m', 'alembic', 'downgrade', 'b8c2d41a9e06'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    async with test_engine.connect() as connection:
        after = await connection.run_sync(columns)
    assert 'interview_rounds' not in after['tables'] and 'amendment_history' not in after['card']
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

@pytest.mark.asyncio
async def test_purge_removes_new_workflow_data_and_question_revisions(test_session_factory):
    from app.db.models import ReviewProgress, InterviewRound, InterviewDraft, InterviewRevision
    from app.services.deletion import execute_purge_job
    ctx = await context(test_session_factory, assessment=True); ids = await criteria(test_session_factory, ctx)
    route = f"/api/v1/applications/{ctx['app_id']}"
    async with client(ctx) as api:
        state = (await api.get(route+'/review-progress')).json()
        assert (await api.put(route+'/review-progress', json={'source_hash':state['source_hash'],'expected_version':0,'reviewed_criterion_ids':ids})).status_code == 200
        state = (await api.get(route+'/interview-rounds/1')).json()
        assert (await api.put(route+'/interview-rounds/1', json={**plan(ids,ctx),'source_hash':state['source_hash']})).status_code == 200
        assert (await screen(api,ctx,ids)).status_code == 201
        async with test_session_factory() as db:
            req = await db.get(Requisition,ctx['req_id'])
            draft = InterviewDraft(application_id=ctx['app_id'],job_id=uuid.uuid4(),created_by=ctx['owner'].id,status='succeeded',source_hash='f'*64,
                source_snapshot={'application_generation':1,'document_id':str(ctx['doc_id']),'sanitized_version_id':str(ctx['sanitized_id']),'rubric_version_id':str(ctx['rubric_id']),'jd_version_id':str(req.current_jd_version_id)},questions_payload={'followups':[]})
            db.add(draft); await db.flush()
            db.add(InterviewRevision(interview_draft_id=draft.id,revision_no=1,followups_payload={'followups':[]},change_reason='Giữ câu hỏi theo năng lực đã duyệt.',created_by=ctx['owner'].id,source_hash='e'*64)); await db.commit()
        deletion = await api.post('/api/v1/deletion-requests',json={'scope':'application','target_id':str(ctx['app_id']),'reason_category':'candidate_request'})
        assert deletion.status_code == 201, deletion.text
    async with test_session_factory() as db:
        await execute_purge_job(db, uuid.UUID(deletion.json()['job_id'])); await db.commit()
        for model in (ReviewProgress, InterviewRound, InterviewDraft):
            assert (await db.execute(select(model).where(model.application_id == ctx['app_id']))).scalars().all() == []


@pytest.mark.asyncio
async def test_jd_change_invalidates_previous_screening_conclusion(test_session_factory):
    ctx = await context(test_session_factory, assessment=True); ids = await criteria(test_session_factory,ctx)
    async with client(ctx) as api:
        assert (await screen(api,ctx,ids)).status_code == 201
        async with test_session_factory() as db:
            req = await db.get(Requisition,ctx['req_id']); req.current_jd_version_id = uuid.uuid4(); await db.commit()
        assert (await api.get(f"/api/v1/applications/{ctx['app_id']}/progress")).json()['stage'] != 'awaiting_interview'

@pytest.mark.asyncio
async def test_submitted_card_reports_stale_after_jd_change(test_session_factory):
    ctx = await context(test_session_factory, assessment=True); ids = await criteria(test_session_factory,ctx)
    route = f"/api/v1/applications/{ctx['app_id']}/interview-scorecards"
    async with client(ctx) as api:
        result = await api.put(route,json={'round_no':1,'expected_version':0,'criteria':card(ids),'submit':True})
        assert result.status_code == 200, result.text
        async with test_session_factory() as db:
            req = await db.get(Requisition,ctx['req_id']); req.current_jd_version_id = uuid.uuid4(); await db.commit()
        assert (await api.get(route)).json()[0]['is_stale'] is True

@pytest.mark.asyncio
async def test_concluded_round_invalidates_invitation_and_cannot_be_invited_again(test_session_factory):
    ctx = await context(test_session_factory, assessment=True); ids = await criteria(test_session_factory,ctx)
    route = f"/api/v1/applications/{ctx['app_id']}"
    async with client(ctx) as api:
        assert (await screen(api,ctx,ids)).status_code == 201
        state = (await api.get(route+'/interview-rounds/1')).json()
        saved = await api.put(route+'/interview-rounds/1',json={**plan(ids,ctx),'source_hash':state['source_hash'],
            'interviewer_ids':[str(ctx['owner'].id)],'starts_at':'2026-10-22T03:00:00+00:00','meeting_location':'https://meet.example.com/synthetic'})
        assert saved.status_code == 200
        assert (await api.put(route+'/interview-scorecards',json={'round_no':1,'expected_version':0,'criteria':card(ids),'submit':True})).status_code == 200
        draft = (await api.post(route+'/email-draft/generate')).json()
        concluded = await api.post(route+'/interview-rounds/1/conclusions',json={'expected_version':saved.json()['row_version'],
            'outcome':'not_advance','reason':'Năng lực được quan sát chưa phù hợp với yêu cầu trọng tâm.'})
        assert concluded.status_code == 201, concluded.text
        assert (await api.get(route+'/email-draft')).status_code == 410
        regenerated = (await api.post(route+'/email-draft/generate')).json()
        result = await api.put(route+'/email-draft',json={'subject':regenerated['subject'],'body':regenerated['body'],'status':'approved',
            'draft_id':regenerated['id'],'expected_version':regenerated['version_no'],'acknowledged_content':True})
        assert result.status_code == 409

@pytest.mark.asyncio
async def test_unassigned_reviewer_cannot_save_draft_and_freeze_plan(test_session_factory):
    ctx = await context(test_session_factory, assessment=True); ids = await criteria(test_session_factory,ctx)
    route = f"/api/v1/applications/{ctx['app_id']}"
    async with client(ctx) as owner, client(ctx,'r') as reviewer:
        state = (await owner.get(route+'/interview-rounds/1')).json()
        payload = {**plan(ids,ctx),'source_hash':state['source_hash'],'interviewer_ids':[str(ctx['owner'].id)]}
        saved = await owner.put(route+'/interview-rounds/1',json=payload); assert saved.status_code == 200
        unauthorized = await reviewer.put(route+'/interview-scorecards',json={'round_no':1,'expected_version':0,'criteria':card(ids),'submit':False})
        assert unauthorized.status_code == 403
        changed = await owner.put(route+'/interview-rounds/1',json={**payload,'expected_version':saved.json()['row_version'],'focus_criterion_ids':ids[1:3]})
        assert changed.status_code == 200, changed.text

async def saved_single_round(api,ctx,ids,number=1,**overrides):
    path=f"/api/v1/applications/{ctx['app_id']}/interview-rounds/{number}"
    state=(await api.get(path)).json()
    response=await api.put(path,json={**plan(ids,ctx),'source_hash':state['source_hash'],'expected_version':state['row_version'],
        'interviewer_ids':[str(ctx['owner'].id)],'starts_at':'2026-10-22T03:00:00+00:00','meeting_location':'https://meet.example.com/synthetic',**overrides})
    assert response.status_code==200,response.text
    return response.json()

@pytest.mark.asyncio
@pytest.mark.parametrize('outcome,stage',[('request_information','waiting_information'),('not_advance','not_advanced')])
async def test_future_plan_does_not_clear_previous_human_wait_or_stop(test_session_factory,outcome,stage):
    ctx=await context(test_session_factory,assessment=True); ids=await criteria(test_session_factory,ctx)
    route=f"/api/v1/applications/{ctx['app_id']}"
    async with client(ctx) as api:
        assert (await screen(api,ctx,ids)).status_code==201
        first=await saved_single_round(api,ctx,ids)
        await saved_single_round(api,ctx,ids,2)
        assert (await api.put(route+'/interview-scorecards',json={'round_no':1,'expected_version':0,'criteria':card(ids),'submit':True})).status_code==200
        result=await api.post(route+'/interview-rounds/1/conclusions',json={'expected_version':first['row_version'],'outcome':outcome,'reason':'Cần đối chiếu thêm các ví dụ thực tế về năng lực trọng tâm.'})
        assert result.status_code==201,result.text
        assert (await api.get(route+'/progress')).json()['stage']==stage
        queue=(await api.get(f"/api/v1/requisitions/{ctx['req_id']}/review-queue")).json()
        assert next(row for row in queue if row['application_id']==str(ctx['app_id']))['workflow_stage']==stage

@pytest.mark.asyncio
async def test_scorecard_amendment_invalidates_next_round_invitation(test_session_factory):
    ctx=await context(test_session_factory,assessment=True); ids=await criteria(test_session_factory,ctx)
    route=f"/api/v1/applications/{ctx['app_id']}"
    async with client(ctx) as api:
        assert (await screen(api,ctx,ids)).status_code==201
        first=await saved_single_round(api,ctx,ids)
        own=(await api.put(route+'/interview-scorecards',json={'round_no':1,'expected_version':0,'criteria':card(ids),'submit':True})).json()
        result=await api.post(route+'/interview-rounds/1/conclusions',json={'expected_version':first['row_version'],'outcome':'advance','reason':'Các ví dụ đã được kiểm chứng đủ để tiếp tục vòng chuyên môn.'})
        assert result.status_code==201,result.text
        await saved_single_round(api,ctx,ids,2)
        draft=(await api.post(route+'/email-draft/generate')).json()
        approved=await api.put(route+'/email-draft',json={'subject':draft['subject'],'body':draft['body'],'status':'approved','draft_id':draft['id'],'expected_version':draft['version_no'],'acknowledged_content':True})
        assert approved.status_code==200,approved.text
        amended=await api.post(f"/api/v1/interview-scorecards/{own['id']}/amend",json={'expected_version':own['row_version'],'criteria':card(ids),'change_reason':'Sửa lại ghi nhận gốc để rà soát kết luận tiếp tục phỏng vấn.'})
        assert amended.status_code==200,amended.text
        assert (await api.get(route+'/email-draft')).status_code==410
        draft=(await api.post(route+'/email-draft/generate')).json()
        approved=await api.put(route+'/email-draft',json={'subject':draft['subject'],'body':draft['body'],'status':'approved','draft_id':draft['id'],'expected_version':draft['version_no'],'acknowledged_content':True})
        assert approved.status_code==409

@pytest.mark.asyncio
@pytest.mark.parametrize('location',['TBD','Sẽ gửi link sau'])
async def test_placeholder_join_details_cannot_approve_invitation(test_session_factory,location):
    ctx=await context(test_session_factory,assessment=True); ids=await criteria(test_session_factory,ctx)
    route=f"/api/v1/applications/{ctx['app_id']}"
    async with client(ctx) as api:
        assert (await screen(api,ctx,ids)).status_code==201
        await saved_single_round(api,ctx,ids,meeting_location=location)
        draft=(await api.post(route+'/email-draft/generate')).json()
        result=await api.put(route+'/email-draft',json={'subject':draft['subject'],'body':draft['body'],'status':'approved','draft_id':draft['id'],'expected_version':draft['version_no'],'acknowledged_content':True})
        assert result.status_code==409
        assert 'EMAIL_SCHEDULE_REQUIRED' in result.text

@pytest.mark.asyncio
async def test_questions_become_stale_when_effective_hr_assessment_changes(test_session_factory):
    from app.db.models import InterviewDraft,HRRevision
    ctx=await context(test_session_factory,assessment=True)
    route=f"/api/v1/applications/{ctx['app_id']}"
    async with client(ctx) as api:
        application=(await api.get(route)).json()
        created=await api.post(route+'/interview-drafts',json={'effective_result':{'kind':'assessment_run','id':application['current_assessment_run_id']}})
        assert created.status_code==202,created.text
        draft_id=uuid.UUID(created.json()['id'])
        async with test_session_factory() as db:
            draft=await db.get(InterviewDraft,draft_id); draft.status='succeeded'; draft.questions_payload={'followups':[]}
            db.add(HRRevision(application_id=ctx['app_id'],base_run_id=uuid.UUID(application['current_assessment_run_id']),document_id=ctx['doc_id'],
                sanitized_version_id=ctx['sanitized_id'],rubric_version_id=ctx['rubric_id'],application_generation=1,revision_no=1,status='finalized',
                criteria_payload={'criteria':[]},summary_reason='Đã điều chỉnh đánh giá theo các bằng chứng trên CV.',created_by=ctx['owner'].id))
            await db.commit()
        detail=(await api.get(f'/api/v1/interview-drafts/{draft_id}')).json()
        assert detail['is_stale'] is True
        assert 'EFFECTIVE_RESULT_CHANGED' in ' '.join(detail['stale_reasons'])
        assert (await api.post(f'/api/v1/interview-drafts/{draft_id}/revisions',json={'followups':[],'change_reason':'Sửa bộ câu hỏi theo đánh giá hiện hành.'})).status_code==409
        assert (await api.post(route+'/interview-drafts',json={'effective_result':{'kind':'assessment_run','id':application['current_assessment_run_id']}})).status_code==409
