"""Isolation is a verified property of the DB, not an environment toggle."""
from dataclasses import replace
import os
from pathlib import Path
import uuid
import pytest
from sqlalchemy import text, select, func, delete
from app.config import get_settings
from app.db.models import Application, AuditEvent, SanitizedVersion, SourceSpan, RequisitionMembership, Organization, Requisition, AssessmentRun, RubricVersion
from app.services.evaluation.benchmark.contracts import PROFILES
from app.services.evaluation.benchmark.dataset import load_inputs, select_runs, canonical_case
from app.services.evaluation.benchmark.isolation import IsolationContext, assert_isolated_database, cleanup_owned_container
from app.services.evaluation.benchmark.seed import seed_cases

DATA = Path(__file__).resolve().parents[3] / 'fixtures/ai_benchmark/v1'

@pytest.fixture
async def owned_context(test_session_factory, tmp_path, monkeypatch):
    settings = get_settings()
    nonce = uuid.uuid4().hex
    root = tmp_path / 'owned'
    root.mkdir()
    (root / '.benchmark-owner').write_text(nonce)
    storage = root / 'storage'
    storage.mkdir()
    monkeypatch.setattr(settings, 'PRIVATE_STORAGE_ROOT', str(storage))
    context = IsolationContext(experiment_id=uuid.uuid4(), container_id='test-owned', nonce=nonce,
        database_name='talentscreen_test', database_url=os.environ['DATABASE_URL'],
        database_sync_url=os.environ['DATABASE_SYNC_URL'], temporary_root=root, storage_root=storage)
    async with test_session_factory() as db:
        await db.execute(text("COMMENT ON DATABASE talentscreen_test IS 'benchmark:" + nonce + "'"))
        await db.commit()
    yield context
    async with test_session_factory() as db:
        org_ids=select(Organization.id).where(Organization.name=='Synthetic AI Benchmark '+str(context.experiment_id))
        req_ids=select(Requisition.id).where(Requisition.organization_id.in_(org_ids))
        app_ids=select(Application.id).where(Application.requisition_id.in_(req_ids))
        await db.execute(delete(AssessmentRun).where(AssessmentRun.application_id.in_(app_ids)))
        await db.execute(delete(RubricVersion).where(RubricVersion.requisition_id.in_(req_ids)))
        await db.execute(delete(Organization).where(Organization.id.in_(org_ids)))
        await db.execute(text('COMMENT ON DATABASE talentscreen_test IS NULL'))
        await db.commit()

@pytest.mark.asyncio
async def test_fake_isolation_flag_cannot_authorize_writes(test_session_factory, owned_context):
    async with test_session_factory() as db:
        for bad in (replace(owned_context, nonce='f'*32),
                    replace(owned_context, database_name='production'),
                    replace(owned_context, storage_root=Path('/tmp')),
                    replace(owned_context, database_url=owned_context.database_url.replace('127.0.0.1','localhost'))):
            with pytest.raises(ValueError, match='ISOLATION'):
                await assert_isolated_database(db, bad)
        before = await db.scalar(select(func.count()).select_from(Application))
        inputs = load_inputs(DATA)
        with pytest.raises(ValueError, match='ISOLATION'):
            await seed_cases(db, inputs, select_runs(inputs,split=None,case_ids=('node-01',), profiles=PROFILES,seed=1),
                             replace(owned_context,nonce='f'*32))
        assert await db.scalar(select(func.count()).select_from(Application)) == before


def test_cleanup_only_stops_owned_container(monkeypatch):
    import app.services.evaluation.benchmark.isolation as isolation
    calls=[]
    def fake(args):
        calls.append(args)
        if args[0] == 'inspect': return 'another-experiment'
        raise AssertionError('must not stop an unrelated container')
    monkeypatch.setattr(isolation, '_docker', fake)
    assert cleanup_owned_container('exact-container-id', 'ours') is False
    assert len(calls)==1
    monkeypatch.setattr(isolation,'_docker',lambda args: calls.append(args) or ('ours' if args[0]=='inspect' else ''))
    assert cleanup_owned_container('exact-container-id','ours') is True
    assert calls[-1] == ['stop', 'exact-container-id']

@pytest.mark.asyncio
async def test_seed_is_synthetic_approved_and_snapshot_consistent(test_session_factory, owned_context):
    inputs=load_inputs(DATA)
    selection=select_runs(inputs,split=None,case_ids=('node-01','ai-01','android-01'),profiles=PROFILES,seed=1)
    async with test_session_factory() as db:
        seeded=await seed_cases(db,inputs,selection,owned_context)
        assert set(seeded)==set(selection.case_ids)
        for case in (c for c in inputs.cases if c.case_id in seeded):
            item=seeded[case.case_id]
            app=await db.get(Application,item.application_id)
            version=await db.get(SanitizedVersion,item.sanitized_version_id)
            assert app.current_document_id==item.document_id
            assert app.current_sanitized_version_id==version.id
            assert version.status.value=='approved'
            expected_id,expected_text,expected_spans=canonical_case(case)
            assert version.id==expected_id and version.canonical_text==expected_text
            spans=(await db.scalars(select(SourceSpan).where(SourceSpan.sanitized_version_id==version.id))).all()
            assert {s.span_id for s in spans}=={s.span_id for s in expected_spans}
            assert all(version.canonical_text[s.start_cp:s.end_cp]==s.text for s in spans)
            assert await db.get(RequisitionMembership,(app.requisition_id,item.ctx.user.id))
        audits=(await db.scalars(select(AuditEvent).where(AuditEvent.action=='benchmark.seed'))).all()
        assert any(a.safe_metadata.get('origin')=='synthetic_design_expected' for a in audits)


def test_wrapper_interruption_cleans_exact_owned_resources(monkeypatch,tmp_path):
    import app.services.evaluation.benchmark.isolation as isolation
    root=tmp_path/'wrapper-owned'
    root.mkdir()
    unrelated=tmp_path/'unrelated'
    unrelated.mkdir()
    owner=None
    stopped=[]
    def fake(args):
        nonlocal owner
        if args[0]=='run':
            owner=args[args.index('--label')+1].split('=',1)[1]
            return 'owned-id'
        if args[0]=='port': return '127.0.0.1:54321'
        if args[0]=='inspect': return owner
        if args[0]=='stop': stopped.append(args[1])
        return ''
    monkeypatch.setattr(isolation.tempfile,'mkdtemp',lambda **kwargs:str(root))
    monkeypatch.setattr(isolation,'_docker',fake)
    monkeypatch.setattr(isolation.subprocess,'run',lambda *a,**k: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        isolation.run_in_isolation(['python','-c','pass'])
    assert stopped==['owned-id']
    assert not root.exists() and unrelated.is_dir()

def test_wrapper_forwards_term_and_waits_before_cleanup(monkeypatch,tmp_path):
    import signal
    import app.services.evaluation.benchmark.isolation as isolation
    root=tmp_path/'term-owned';root.mkdir()
    owner=None;events=[]
    def fake(args):
        nonlocal owner
        if args[0]=='run':owner=args[args.index('--label')+1].split('=',1)[1];return 'owned-id'
        if args[0]=='port':return '127.0.0.1:54321'
        if args[0]=='inspect':return owner
        if args[0]=='stop':events.append('cleanup')
        return ''
    class Child:
        returncode=130
        def poll(self):return None
        def send_signal(self,sig):events.append('signal')
        def wait(self,timeout=None):
            if not events:
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
            events.append('wait');return 130
    monkeypatch.setattr(isolation.tempfile,'mkdtemp',lambda **kw:str(root))
    monkeypatch.setattr(isolation,'_docker',fake)
    monkeypatch.setattr(isolation.subprocess,'run',lambda *a,**k:type('Result',(),{'returncode':0})())
    monkeypatch.setattr(isolation.subprocess,'Popen',lambda *a,**k:Child())
    assert isolation.run_in_isolation(['python','child'])==130
    assert events==['signal','wait','wait','cleanup']
