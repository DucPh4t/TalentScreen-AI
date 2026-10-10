from pathlib import Path
from decimal import Decimal
import pytest
from app.services.evaluation.benchmark.runner import main
from app.services.evaluation.benchmark.dataset import load_inputs,select_runs
from app.services.assessment.policy import benchmark_policy
from app.services.evaluation.benchmark.preflight import plan_budget,context_bound
from tests.test_rerank_kernel import policy
ROOT=Path(__file__).resolve().parents[3]


def test_extended_cli_plan_preserves_off_and_bounds_cost(capsys):
    args=['plan','--dataset',str(ROOT/'fixtures/ai_benchmark/golden_100'),'--provider','mock','--profiles','hybrid,hybrid_agent',
        '--cases','backend-003','--embedding-mode','scripted','--retrieval-version','v2','--max-cost-usd','1']
    assert main(args+['--rerank-mode','rerank','--reranker-provider','scripted'])==0
    import json
    result=json.loads(capsys.readouterr().out)
    assert result['reranking']['reranker_provider']=='scripted'
    assert result['reranking']['model_quality']=='unmeasured'
    assert Decimal(result['reranking']['budget']['total_upper_usd'])==0
    assert main(args+['--rerank-mode','gate_experiment','--reranker-provider','scripted'])==0


def test_combined_preflight_rejects_budget_and_uncertainty():
    from app.services.evaluation.benchmark.reranking import plan_rerank_budget
    inputs=load_inputs(ROOT/'fixtures/ai_benchmark/golden_100')
    selection=select_runs(inputs,split=None,case_ids=('backend-003',),profiles=('hybrid',),seed=1)
    primary=plan_budget(inputs,selection,{'hybrid':benchmark_policy('hybrid',retrieval_version='v2')},model='mock',cap_usd=Decimal('1'),bound=context_bound('mock'))
    assert plan_rerank_budget(primary,selection,policy=policy(),reranker_provider='scripted',cap_usd=Decimal('1')).total_upper_usd==0
    with pytest.raises(ValueError):plan_rerank_budget(primary,selection,policy=policy(),reranker_provider='jev',cap_usd=Decimal('.001'))


def test_reranking_manifest_extension_is_strict():
    from app.services.evaluation.benchmark.reranking import RerankingManifestData
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RerankingManifestData.model_validate({'mode':'rerank','unexpected':'raw_prompt'})
