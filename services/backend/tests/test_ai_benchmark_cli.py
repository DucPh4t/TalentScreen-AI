from pathlib import Path
import pytest
from app.services.evaluation.benchmark.runner import DEFAULT_DATASET, main
from app.services.evaluation.benchmark.dataset import load_inputs
from app.services.evaluation.benchmark.mock_provider import BenchmarkMockProvider
DATA=Path(__file__).resolve().parents[3]/'fixtures/ai_benchmark/golden_100'


def test_default_cli_uses_only_the_frozen_100_case_multi_role_dataset(capsys):
    import json
    expected_role_counts = {
        'senior_ai_engineer': 20,
        'software_development_manager': 20,
        'java_backend_developer': 20,
        'mobile_web_qa': 20,
        'agentic_engineer': 20,
    }
    assert main(['validate']) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated['cases'] == 100
    assert validated['role_counts'] == expected_role_counts
    assert validated['criteria_per_role'] == {role: 6 for role in expected_role_counts}
    assert validated['criteria_total'] == 30
    assert validated['reference_not_hr_validated'] is True
    assert validated['hiring_quality_claim'] == 'not_evaluated'
    assert main(['plan', '--provider', 'mock', '--embedding-mode', 'scripted', '--profiles', 'full_text']) == 0
    plan = json.loads(capsys.readouterr().out)
    assert len(plan['combinations']) == 100
    assert {row['case_id'] for row in plan['combinations']} == {
        case.case_id for case in load_inputs(DEFAULT_DATASET).cases
    }

def test_cli_plan_validate_and_invalid_report_never_call_provider(monkeypatch,tmp_path,capsys):
    def forbidden(*a,**k):raise AssertionError('provider called')
    monkeypatch.setattr(BenchmarkMockProvider,'complete',forbidden)
    assert main(['validate','--dataset',str(DATA)])==0
    assert main(['plan','--dataset',str(DATA),'--provider','mock','--cases','backend-008','--embedding-mode','scripted'])==0
    assert main(['report','--input',str(tmp_path/'missing'),'--output',str(tmp_path/'report')])==2
    for flags in (['--profiles','unknown'],['--cases','unknown'],['--provider','unknown']):
        assert main(['plan','--dataset',str(DATA),'--provider','mock',*flags])==2
    assert main(['run','--dataset',str(DATA),'--provider','mock','--cases','backend-008','--embedding-mode','scripted','--output',str(tmp_path/'out')])==2
    assert 'synthetic' in capsys.readouterr().out.lower()


@pytest.fixture
def live_plan_settings(monkeypatch,tmp_path):
    from app.config import get_settings
    from app.services.evaluation.benchmark import preflight
    from tests.test_ai_benchmark_budget import byte_bound
    from datetime import date
    settings=get_settings()
    monkeypatch.setattr(settings,'DEEPSEEK_MODEL','deepseek-flash')
    monkeypatch.setattr(settings,'DEEPSEEK_BASE_URL','https://api.deepseek.com')
    monkeypatch.setattr(settings,'DEEPSEEK_API_KEY','synthetic-fixture-key')
    monkeypatch.setattr(preflight,'verify_utf8_artifacts',lambda _:byte_bound())
    monkeypatch.setattr(preflight,'resolve_cached_embedding_revision',lambda:'a'*40)
    proof=tmp_path/'pricing-proof.json'
    proof.write_text('{"verified_at":"2026-10-09"}')
    monkeypatch.setattr(preflight,'PROOF_REFERENCE',str(proof))
    class FrozenDate(date):
        @classmethod
        def today(cls):return cls(2026,10,9)
    monkeypatch.setattr(preflight,'date',FrozenDate)
    from app.services.llm.provider import DeepSeekHTTPXProvider
    def forbidden(*a,**k):raise AssertionError('planning must never construct a network provider')
    monkeypatch.setattr(DeepSeekHTTPXProvider,'__init__',forbidden)
    return settings


@pytest.mark.parametrize('failure',('provider','missing_key','missing_e5'))
def test_live_plan_checks_prerequisites_before_success(failure,live_plan_settings,monkeypatch,capsys):
    from app.services.evaluation.benchmark import preflight
    if failure=='provider':live_plan_settings.DEEPSEEK_BASE_URL='https://unverified.example.test?secret=PRIVATE_MARKER'
    elif failure=='missing_key':live_plan_settings.DEEPSEEK_API_KEY=None
    else:
        def missing():raise ValueError('BENCHMARK_E5_NOT_CACHED')
        monkeypatch.setattr(preflight,'resolve_cached_embedding_revision',missing)
    result=main(['plan','--dataset',str(DATA),'--provider','deepseek','--cases','backend-008'])
    assert result==2
    output=capsys.readouterr()
    assert 'PRIVATE_MARKER' not in output.err+output.out


def test_live_plan_reports_verified_prerequisites_without_network(live_plan_settings,capsys):
    import json
    assert main(['plan','--dataset',str(DATA),'--provider','deepseek','--cases','backend-008'])==0
    payload=json.loads(capsys.readouterr().out)
    assert payload['execution_prerequisites']['verified'] is True
    assert payload['execution_prerequisites']['embedding_revision']=='a'*40
    assert payload['execution_prerequisites']['embedding_mode']=='real'
    assert 'synthetic-fixture-key' not in json.dumps(payload)
