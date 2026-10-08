from pathlib import Path
import pytest
from app.services.evaluation.benchmark.runner import main
from app.services.evaluation.benchmark.mock_provider import BenchmarkMockProvider
DATA=Path(__file__).resolve().parents[3]/'fixtures/ai_benchmark/v1'

def test_cli_plan_validate_and_invalid_report_never_call_provider(monkeypatch,tmp_path,capsys):
    def forbidden(*a,**k):raise AssertionError('provider called')
    monkeypatch.setattr(BenchmarkMockProvider,'complete',forbidden)
    assert main(['validate','--dataset',str(DATA)])==0
    assert main(['plan','--dataset',str(DATA),'--provider','mock','--cases','node-01'])==0
    assert main(['report','--input',str(tmp_path/'missing'),'--output',str(tmp_path/'report')])==2
    for flags in (['--profiles','unknown'],['--cases','unknown'],['--provider','unknown']):
        assert main(['plan','--dataset',str(DATA),'--provider','mock',*flags])==2
    assert main(['run','--dataset',str(DATA),'--provider','mock','--cases','node-01','--embedding-mode','scripted','--output',str(tmp_path/'out')])==2
    assert 'synthetic' in capsys.readouterr().out.lower()
