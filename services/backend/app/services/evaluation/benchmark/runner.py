"""Sequential, isolated experiments through the real assessment services."""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import uuid
from .contracts import PROFILES,RunManifest,RunRecord,CriterionObservation,InvocationRecord
from .dataset import load_inputs,select_runs
from .artifacts import create_output,atomic_json,append_record,append_event

def now():return datetime.now(timezone.utc).isoformat()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def assert_frozen(inputs):
    current=load_inputs(inputs.root)
    if current.manifest_hash!=inputs.manifest_hash or current.hashes!=inputs.hashes:
        raise ValueError('DATASET_HASH_MISMATCH')

class RecordingProvider:
    def __init__(self,provider,db,job_id,inputs,output):
        self.provider=provider;self.db=db;self.job_id=job_id;self.inputs=inputs;self.output=output;self.results={}
    async def complete(self,request):
        from sqlalchemy import select
        from app.db.models import LLMInvocation
        assert_frozen(self.inputs)
        pending=(await self.db.scalars(select(LLMInvocation).where(LLMInvocation.job_id==self.job_id,
            LLMInvocation.status.in_(['reserved','admitted'])).order_by(LLMInvocation.created_at.desc()))).first()
        if pending is None:raise ValueError('BENCHMARK_ADMISSION_MISSING')
        entry={'event':'admitted','invocation_id':str(pending.id),'job_id':str(self.job_id),'logical_step':pending.logical_step,
            'attempt_no':pending.attempt_no,'requested_model':request.model,'request_hash':pending.request_hash,
            'reserved_usd':str(pending.cost_reserved),'at':now()}
        append_event(self.output/'admissions.jsonl',entry)
        await self.db.commit()  # close the metadata read before provider I/O/settlement
        try:result=await self.provider.complete(request)
        except BaseException as e:
            append_event(self.output/'admissions.jsonl',{'event':'provider_failed','invocation_id':str(pending.id),
                'error_type':type(e).__name__,'at':now()})
            raise
        self.results[pending.id]=result
        append_event(self.output/'admissions.jsonl',{'event':'provider_returned','invocation_id':str(pending.id),
            'reported_model':result.reported_model,'input_tokens':result.input_tokens,'output_tokens':result.output_tokens,
            'cached_input_tokens':result.cached_input_tokens,'provider_latency_ms':result.latency_ms,'at':now()})
        return result

class BenchmarkMockRecordingProvider(RecordingProvider):pass
class DeepSeekRecordingProvider(RecordingProvider):pass

async def run_experiment(db,inputs,selection,context,*,provider,budget_plan,output,embedding_mode='real'):
    from sqlalchemy import select
    from app.config import get_settings
    from app.db.models import AssessmentRun,CriterionAssessment,CriterionEvidence,LLMInvocation,Job,BudgetReservation
    from app.domain.enums import BudgetScope,JobStatus,LLMInvocationStatus
    from app.schemas.assessment import AssessmentRunCreateRequest,AssessmentOutputSchema
    from app.services.assessment.service import create_assessment_run,execute_assessment_job
    from app.services.assessment.policy import benchmark_policy
    from app.services.assessment.prompt import get_assessment_prompt
    from app.services.agent.assessment_graph import _AGENT_PROMPTS,AGENT_PROMPT_VERSION
    from app.services.assessment.diagnostics import AssessmentDiagnostics
    from app.services.embedding import EMBEDDING_CONFIG_ID
    from app.services.llm.ledger import get_or_create_active_budget_period,settle_budget
    from app.services.llm.types import StrictReservationPolicy
    from app.services.observability import trace_span
    from .isolation import assert_isolated_database
    from .seed import seed_cases
    from .mock_provider import scripted_embeddings,BenchmarkMockProvider
    from .preflight import plan_budget
    output=Path(output)
    if output.exists() or output.is_symlink():raise ValueError('BENCHMARK_OUTPUT_EXISTS')
    await assert_isolated_database(db,context)
    settings=get_settings()
    is_mock=budget_plan.model=='mock'
    if settings.APP_ENV!='sandbox' or settings.JEV_MODE!='off' or settings.DEEPSEEK_MODEL!=budget_plan.model:
        raise ValueError('BENCHMARK_CONFIG_MISMATCH')
    if embedding_mode not in {'scripted','real'} or (not is_mock and embedding_mode!='real'):
        raise ValueError('BENCHMARK_SCRIPTED_LIVE_FORBIDDEN')
    policies={p:benchmark_policy(p) for p in selection.profiles}
    recalculated=plan_budget(inputs,selection,policies,model=budget_plan.model,cap_usd=budget_plan.cap_usd,bound=budget_plan.bound)
    if recalculated!=budget_plan or not budget_plan.admitted:raise ValueError('BENCHMARK_BUDGET_PLAN_REJECTED')
    assert_frozen(inputs)
    period=await get_or_create_active_budget_period(db,BudgetScope.DEVELOPMENT)
    if period.limit_usd!=budget_plan.cap_usd:raise ValueError('BENCHMARK_CAP_MISMATCH')
    if period.spent_usd or period.reserved_usd:raise ValueError('BENCHMARK_NO_RESUME')
    create_output(output)
    seeded=await seed_cases(db,inputs,selection,context)
    await db.commit()
    manifest=RunManifest(experiment_id=context.experiment_id,status='running',mode='contract_only' if is_mock else 'live_model',
        model_quality='unmeasured' if is_mock else 'synthetic_reference_only',provider='mock' if is_mock else 'deepseek',
        requested_model=budget_plan.model,embedding_mode=embedding_mode,selection=selection,dataset_hash=inputs.manifest_hash,
        dataset_files=inputs.hashes,policies={p:policy.to_snapshot() for p,policy in policies.items()},
        provenance={'effective_prompt_sha256':hashlib.sha256((get_assessment_prompt('assessment-v1.6.0')+'\n\n'+_AGENT_PROMPTS[AGENT_PROMPT_VERSION]).encode()).hexdigest(),
            'schema_sha256':digest(AssessmentOutputSchema.model_json_schema()),'embedding_config':EMBEDDING_CONFIG_ID,
            'temperature':0,'thinking':'disabled','max_output_tokens':4096,'concurrency':1,'repetitions':1,
            'reference_origin':'synthetic_design_expected','invoice_usd':None},budget_plan=budget_plan,
        budget_period_id=period.id,started_at=now(),counts={'planned':len(selection.combinations)})
    atomic_json(output/'manifest.json',manifest)
    strict=StrictReservationPolicy(period.id,budget_plan.cap_usd,budget_plan.bound,budget_plan.model)
    stop=None;interrupted=False;records=[]
    with scripted_embeddings(embedding_mode=='scripted'):
        for case_id,profile in selection.combinations:
            if stop:
                record=RunRecord(case_id=case_id,profile=profile,status='skipped',error_code=stop,policy_hash=policies[profile].digest)
                append_record(output/'runs.jsonl',record);records.append(record)
                continue
            run=None;wrapper=None;trace_id=None
            diagnostic=AssessmentDiagnostics({c.id for c in inputs.roles[next(c.role_family for c in inputs.cases if c.case_id==case_id)].criteria})
            try:
                assert_frozen(inputs)
                item=seeded[case_id]
                response=await create_assessment_run(db,item.application_id,AssessmentRunCreateRequest(
                    sanitized_version_id=item.sanitized_version_id,rubric_version_id=item.rubric_version_id),item.ctx,execution_policy=policies[profile])
                await db.commit()
                run=await db.get(AssessmentRun,response.id)
                wrapper=(BenchmarkMockRecordingProvider if is_mock else DeepSeekRecordingProvider)(provider,db,run.job_id,inputs,output)
                with trace_span('benchmark_combination',metadata={}) as span:
                    trace_id=uuid.UUID(span.run_id) if span.run_id else None
                    await execute_assessment_job(db,run.job_id,provider_override=wrapper,diagnostics=diagnostic,strict_reservation_policy=strict)
                await db.commit()
                # Hash changes during the final response also invalidate the batch.
                assert_frozen(inputs)
            except (KeyboardInterrupt,SystemExit,asyncio.CancelledError):
                interrupted=True;stop='BENCHMARK_INTERRUPTED'
            except Exception as e:
                stop='DATASET_HASH_MISMATCH' if 'DATASET_' in str(e) else 'BENCHMARK_EXECUTION_FAILED'
                await db.rollback()
            observations={};invocations=[]
            if run is not None:
                await db.refresh(run)
                if interrupted:
                    run.status='failed';run.failure_code='BENCHMARK_INTERRUPTED';run.completed_at=datetime.now(timezone.utc)
                    reservations=(await db.scalars(select(BudgetReservation).where(BudgetReservation.job_id==run.job_id,
                        BudgetReservation.status=='reserved'))).all()
                    for reservation in reservations:await settle_budget(db,reservation.id,Decimal(0),outcome_unknown=True)
                    outstanding=(await db.scalars(select(LLMInvocation).where(LLMInvocation.job_id==run.job_id,
                        LLMInvocation.status.in_(['reserved','admitted'])))).all()
                    for invocation in outstanding:invocation.status=LLMInvocationStatus.OUTCOME_UNKNOWN
                criteria=(await db.scalars(select(CriterionAssessment).where(CriterionAssessment.run_id==run.id))).all()
                evidence=(await db.scalars(select(CriterionEvidence).where(CriterionEvidence.run_id==run.id))).all()
                if run.status=='succeeded' and not stop:
                    observations={c.criterion_id:CriterionObservation(status=c.status.value,score=c.score,
                        evidence_ids=tuple(e.span_id for e in evidence if e.criterion_id==c.criterion_id),
                        clarification_count=len(c.missing_information or [])) for c in criteria}
                llms=(await db.scalars(select(LLMInvocation).where(LLMInvocation.job_id==run.job_id).order_by(LLMInvocation.created_at))).all()
                for invocation in llms:
                    result=wrapper.results.get(invocation.id) if wrapper else None
                    invocations.append(InvocationRecord(invocation_id=invocation.id,logical_step=invocation.logical_step,
                        attempt_no=invocation.attempt_no,status=invocation.status.value,requested_model=budget_plan.model,
                        reported_model=result.reported_model if result else None,input_tokens=invocation.input_tokens,output_tokens=invocation.output_tokens,
                        cached_input_tokens=result.cached_input_tokens if result else None,provider_latency_ms=result.latency_ms if result else None,
                        reserved_usd=invocation.cost_reserved,estimated_peak_usd=invocation.cost_actual,rate_card_version=invocation.rate_card_version))
                if any(i.status in {'reserved','admitted','outcome_unknown'} for i in invocations) and not stop:
                    stop=run.failure_code or 'BENCHMARK_OUTCOME_PENDING'
                if run.status!='succeeded' and not stop:
                    safe_failures={'ASSESSMENT_OUTPUT_INVALID','AGENT_OUTPUT_INVALID','LLMMalformedJSONError','LLMTruncatedError','LLMEmptyResponseError','LLMRefusalError'}
                    if run.failure_code not in safe_failures:stop=run.failure_code or 'BENCHMARK_EXECUTION_FAILED'
                job=await db.get(Job,run.job_id)
                job.status=JobStatus.SUCCEEDED if observations else JobStatus.FAILED
                job.last_error_code=run.failure_code
                await db.commit()
            status='interrupted' if interrupted else ('accepted' if observations else 'failed')
            source={k:run.snapshot[k] for k in ('application_id','document_id','sanitized_version_id','sanitized_sha256','rubric_version_id','application_generation')} if run else {}
            record=RunRecord(case_id=case_id,profile=profile,status=status,error_code=stop or (run.failure_code if run else None),
                run_id=run.id if run else None,job_id=run.job_id if run else None,source_snapshot_hash=digest(source) if source else None,
                source_ids={k:str(v) for k,v in source.items()},policy_hash=policies[profile].digest,criteria=observations,
                diagnostics=diagnostic.snapshot(),invocations=tuple(invocations),tool_execution_count=(run.execution_trace or {}).get('tool_execution_count',0) if run else 0,
                repair_count=(run.execution_trace or {}).get('repair_count',0) if run else 0,trace_id=trace_id)
            append_record(output/'runs.jsonl',record);records.append(record)
            atomic_json(output/'manifest.json',manifest.model_copy(update={'counts':{'planned':len(selection.combinations),'recorded':len(records)}}))
    await db.refresh(period)
    all_invocations=[i for r in records for i in r.invocations]
    final_status='interrupted' if interrupted else ('complete' if all(r.status=='accepted' for r in records) else 'partial')
    manifest=manifest.model_copy(update={'status':final_status,'completed_at':now(),'stop_code':stop,
        'financial':{'spent_peak_estimate_usd':str(period.spent_usd),'held_usd':str(period.reserved_usd),
            'unresolved_invocations':sum(i.status in {'reserved','admitted','outcome_unknown'} for i in all_invocations),
            'invoice_usd':None},'counts':{'planned':len(selection.combinations),**{s:sum(r.status==s for r in records) for s in ('accepted','failed','skipped','interrupted')}}})
    atomic_json(output/'manifest.json',manifest)
    return manifest

class ArgumentParser(argparse.ArgumentParser):
    def error(self,message):raise ValueError('CLI_ARGUMENT_INVALID')

def parser():
    p=ArgumentParser(description='Synthetic production-pipeline AI benchmark')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('validate','plan','run'):
        q=sub.add_parser(name);q.add_argument('--dataset',type=Path,required=True)
        if name!='validate':
            q.add_argument('--provider',choices=('mock','deepseek'),required=True)
            q.add_argument('--profiles',default='all')
            group=q.add_mutually_exclusive_group();group.add_argument('--split',choices=('development','public_test','all'));group.add_argument('--cases')
            q.add_argument('--seed',type=int,default=20261008)
            q.add_argument('--max-cost-usd',type=Decimal,default=Decimal(5))
        if name=='run':
            q.add_argument('--output',type=Path,required=True);q.add_argument('--embedding-mode',choices=('real','scripted'),default='real')
    q=sub.add_parser('report');q.add_argument('--input',type=Path,required=True);q.add_argument('--output',type=Path,required=True)
    q.add_argument('--dataset',type=Path,default=Path('fixtures/ai_benchmark/v1'))
    return p

def main(argv=None):
    try:
        args=parser().parse_args(argv)
        if args.command=='report':
            if not (args.input/'manifest.json').is_file():raise ValueError('REPORT_INPUT_MISSING')
            from .reporting import generate_reports
            generate_reports(args.input,args.output,args.dataset)
            return 0
        inputs=load_inputs(args.dataset)
        if args.command=='validate':
            from .dataset import load_references
            load_references(inputs.root,inputs)
            print(json.dumps({'origin':'synthetic_design_expected','cases':len(inputs.cases),'hash':inputs.manifest_hash}))
            return 0
        selection=select_runs(inputs,split=args.split or (None if args.cases else 'development'),
            case_ids=tuple(args.cases.split(',')) if args.cases else (),profiles=PROFILES if args.profiles=='all' else tuple(args.profiles.split(',')),seed=args.seed)
        from .preflight import plan_budget,context_bound,verify_utf8_artifacts,validate_live_preflight,embedding_cache_available
        from app.services.assessment.policy import benchmark_policy
        from app.config import get_settings
        model='mock' if args.provider=='mock' else get_settings().DEEPSEEK_MODEL
        try:bound=verify_utf8_artifacts(Path('reports/ai-benchmark-cache'))
        except ValueError:bound=context_bound(model)
        plan=plan_budget(inputs,selection,{p:benchmark_policy(p) for p in selection.profiles},model=model,cap_usd=args.max_cost_usd,bound=bound)
        if args.command=='plan':
            print(plan.model_dump_json(indent=2));return 0 if plan.admitted else 2
        from .isolation import IsolationContext
        try:context=IsolationContext.from_environment()
        except (KeyError,ValueError):raise ValueError('BENCHMARK_ISOLATION_REQUIRED')
        if args.output.exists():raise ValueError('BENCHMARK_OUTPUT_EXISTS')
        if args.provider=='deepseek':
            from urllib.parse import urlparse
            proof=json.loads(Path('docs/evaluation/deepseek-token-bound.json').read_text())
            validate_live_preflight(plan,provider_host=urlparse(get_settings().DEEPSEEK_BASE_URL).hostname,
                pricing_verified_at=proof['verified_at'],model_available_locally=embedding_cache_available())
            if args.embedding_mode!='real':raise ValueError('BENCHMARK_SCRIPTED_LIVE_FORBIDDEN')
        # These settings apply only in the disposable child; never edit .env.
        os.environ.update(APP_ENV='sandbox',JEV_MODE='off',DEV_EVAL_BUDGET_USD=str(args.max_cost_usd),DEEPSEEK_MODEL=model,
            HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
        if args.provider=='mock':os.environ.update(LLM_PROVIDER='mock',LANGSMITH_TRACING='false')
        import app.config as configuration
        configuration._settings=None
        from app.db.session import get_session_factory
        from app.services.llm.provider import DeepSeekHTTPXProvider
        from .mock_provider import BenchmarkMockProvider
        provider=BenchmarkMockProvider() if args.provider=='mock' else DeepSeekHTTPXProvider()
        async def execute():
            loop=asyncio.get_running_loop();task=asyncio.current_task()
            for sig in (signal.SIGINT,signal.SIGTERM):loop.add_signal_handler(sig,task.cancel)
            try:
                async with get_session_factory()() as db:
                    return await run_experiment(db,inputs,selection,context,provider=provider,budget_plan=plan,output=args.output,embedding_mode=args.embedding_mode)
            finally:
                for sig in (signal.SIGINT,signal.SIGTERM):loop.remove_signal_handler(sig)
        manifest=asyncio.run(execute())
        print(json.dumps({'status':manifest.status,'counts':manifest.counts,'financial':manifest.financial}))
        return 0 if manifest.status=='complete' else 130 if manifest.status=='interrupted' else 3
    except (ValueError,FileNotFoundError,ImportError) as e:
        # Only fixed error codes, never credentials/provider/SQL exception strings.
        code=str(e) if isinstance(e,ValueError) and str(e).replace('_','').isalnum() else 'BENCHMARK_INVALID_INPUT'
        print(code,file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
