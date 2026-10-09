from datetime import date
import copy
import pytest
from app.config import Settings
from app.services.assessment.policy import benchmark_policy


def valid_settings(**changes):
    values=dict(LLM_PROVIDER='mock',JEV_MODE='off',JEV_RERANK_MODE='rerank',RAG_MODE='hybrid',
        RAG_PIPELINE_VERSION='v2',JEV_API_KEY='synthetic',JEV_DATA_PROCESSING_APPROVED=True,
        JEV_MODEL='typesafe/jev-1.13',JEV_INPUT_PRICE_PER_MILLION_USD=.042,
        JEV_RATE_CARD_VERIFIED_AT=date.today().isoformat(),JEV_RERANK_ACCEPTED_MODELS=['typesafe/jev-1.13-20260917'])
    return Settings(_env_file=None,**(values|changes))


def test_absent_policy_is_off_without_changing_legacy_digest():
    from app.services.reranking.policy import load_rerank_policy
    policy=benchmark_policy('hybrid')
    before=policy.digest
    snapshot={'assessment_execution_policy':policy.to_snapshot()}
    assert load_rerank_policy(snapshot).mode=='off'
    assert policy.digest==before
    assert 'reranking_policy' not in snapshot


def test_explicit_policy_hash_mismatch_fails():
    from app.services.reranking.policy import freeze_rerank_policy,load_rerank_policy
    p=freeze_rerank_policy(valid_settings())
    snapshot={'reranking_policy':p.model_dump(mode='json'),'reranking_policy_hash':p.digest}
    assert load_rerank_policy(snapshot)==p
    broken=copy.deepcopy(snapshot); broken['reranking_policy']['mode']='shadow'
    with pytest.raises(ValueError,match='RERANK_POLICY_INVALID'): load_rerank_policy(broken)


@pytest.mark.parametrize('changes',[{'RAG_MODE':'full_text_baseline'}, {'RAG_PIPELINE_VERSION':'v1'},
    {'JEV_RERANK_ACCEPTED_MODELS':[]}, {'JEV_DATA_PROCESSING_APPROVED':False},
    {'JEV_INPUT_PRICE_PER_MILLION_USD':float('nan')}])
def test_enabled_policy_requires_v2_hybrid_and_verified_provider(changes):
    from app.services.reranking.policy import freeze_rerank_policy
    with pytest.raises(ValueError): freeze_rerank_policy(valid_settings(**changes))


def test_gate_rejected_outside_sandbox():
    from app.services.reranking.policy import freeze_rerank_policy
    settings=valid_settings(JEV_RERANK_MODE='gate_experiment')
    settings.APP_ENV='pilot'
    with pytest.raises(ValueError): freeze_rerank_policy(settings)


def test_old_shadow_and_reranker_are_mutually_exclusive():
    with pytest.raises(ValueError):
        Settings(_env_file=None,LLM_PROVIDER='mock',JEV_MODE='shadow',JEV_RERANK_MODE='rerank',
            JEV_API_KEY='synthetic',JEV_DATA_PROCESSING_APPROVED=True,
            JEV_INPUT_PRICE_PER_MILLION_USD=.042,JEV_RATE_CARD_VERIFIED_AT=date.today().isoformat())

@pytest.mark.parametrize('changes',[{'accepted_models':[]},{'rate_per_million_usd':0},{'rate_verified_at':None},
    {'endpoint':'http://unapproved.example/api'}, {'provider_kind':'scripted','accepted_models':['real-live-model']}])
def test_enabled_snapshot_cannot_bypass_provider_contract(changes):
    from app.services.reranking.contracts import RerankPolicy
    from tests.test_rerank_kernel import policy
    raw=policy().model_dump(mode='json');raw.update(changes)
    with pytest.raises(ValueError):RerankPolicy.model_validate(raw)
