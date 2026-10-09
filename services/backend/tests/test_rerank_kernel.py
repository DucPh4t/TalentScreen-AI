from datetime import date
import pytest
from app.services.reranking.contracts import ApprovedCriterion,PassagePair,RerankPolicy,PairJudgment,OPTIONS,canonical


def pair(n,c='c',text='Built an API',section=None,rrf=None):
    return PassagePair(pair_id=f'{c}-{n}',criterion=ApprovedCriterion(criterion_id=c,label='API',description='Design HTTP APIs'),
        chunk_id=f'chunk-{n}',chunk_index=n,text=text,span_ids=(f'span-{n}',),section=section,rrf_score=rrf if rrf is not None else 1/(60+n))


def judgment(p,choice='substantive_evidence',confidence=1.0,probs=None):
    return PairJudgment(pair_id=p.pair_id,choice=choice,confidence=confidence,
        probabilities=probs or {k:float(k==choice) for k in OPTIONS},reported_model='jev-1.13.0')


def policy(mode='rerank'):
    return RerankPolicy(mode=mode,accepted_models=('jev-1.13.0',),rate_per_million_usd=.042,rate_verified_at=date.today().isoformat())


def test_utility_and_protected_limiting_unscored_slots():
    from app.services.reranking.selection import utility,rank_and_select
    ps=[pair(n) for n in range(8)]
    j=judgment(ps[0],probs=dict(zip(OPTIONS,[.4,.2,.2,.1,.1])))
    assert utility(j)==pytest.approx(.685)
    js=tuple(judgment(p) for p in ps[:6])+(judgment(ps[6],'limiting_evidence'),)
    r=rank_and_select(tuple(ps),js,policy(),stage='initial')
    selected=r.selected_pair_ids_by_criterion['c']
    assert len(selected)==4 and 'c-6' in selected and 'c-7' in selected
    assert r.ordered_pair_ids_by_criterion['c'][:2]==('c-0','c-1')


def test_all_unscored_preserves_diverse_baseline():
    from app.services.reranking.selection import rank_and_select
    ps=tuple(pair(n,section='projects' if n<4 else 'work') for n in range(8))
    r=rank_and_select(ps,(),policy(),stage='initial')
    assert r.status=='not_scored_bound'
    assert r.selected_pair_ids_by_criterion['c']==('c-0','c-4','c-1','c-2')


@pytest.mark.parametrize('prob,confidence,excluded',[(.95,.8,True),(.949,.8,False),(.95,.799,False)])
def test_gate_excludes_only_confident_unrelated(prob,confidence,excluded):
    from app.services.reranking.selection import rank_and_select
    p=pair(0);probs={k:0.0 for k in OPTIONS};probs['unrelated']=prob;probs['unclear']=1-prob
    j=judgment(p,'unrelated',confidence,probs)
    r=rank_and_select((p,),(j,),policy('gate_experiment'),stage='initial')
    assert bool(r.selected_pair_ids_by_criterion['c']) is not excluded
    for kind in ('limiting_evidence','unclear'):
        r=rank_and_select((p,),(judgment(p,kind),),policy('gate_experiment'),stage='initial')
        assert r.selected_pair_ids_by_criterion['c']==('c-0',)


def test_round_robin_byte_bounds_and_exact_quotes():
    from app.services.reranking.planner import plan_batches
    pools={f'c{c}':tuple(pair(n,f'c{c}',text='Kinh nghiệm xây dựng hệ thống. '*180) for n in range(8)) for c in range(12)}
    plan=plan_batches(pools,policy(),remaining_calls=9,focus_ids=('c2',))
    assert len(plan.batches)<=9
    first={p.criterion.criterion_id for b in plan.batches for p in b.pairs}
    assert first==set(pools)
    for b in plan.batches:
        assert len(b.payload['questions'])<=20
        assert len(canonical(b.payload['state']).encode())<=16384
        assert len(canonical(b.payload).encode())<=32768
        for i,p in enumerate(b.pairs):
            assert b.payload['state']['pairs'][i]['passage']==p.text
            assert f'state.pairs[{i}]' in b.payload['questions'][p.pair_id]['instructions']
    huge=pair(999,text='界'*17000)
    p=plan_batches({'c':(huge,)},policy(),remaining_calls=9,focus_ids=())
    assert not p.batches and p.unscored_pair_ids==(huge.pair_id,)


def test_strict_answer_membership_identity_and_choice():
    from app.services.reranking.prompt import validate_pair_judgments
    p=pair(1)
    a=dict(type='choice',choice='substantive_evidence',confidence=1.0,probabilities={k:float(k=='substantive_evidence') for k in OPTIONS})
    body=dict(model='jev-1.13.0',answers={p.pair_id:a})
    assert validate_pair_judgments(body,(p,),policy())[0].choice=='substantive_evidence'
    for bad in ({**body,'answers':{}},{**body,'model':'rolling'},
        {**body,'answers':{'different':a}}, {**body,'answers':{p.pair_id:{**a,'choice':'unrelated'}}},
        {**body,'answers':{p.pair_id:{**a,'confidence':True}}},
        {**body,'answers':{p.pair_id:{**a,'probabilities':{**a['probabilities'],'unclear':float('nan')}}}}):
        with pytest.raises(ValueError): validate_pair_judgments(bad,(p,),policy())
