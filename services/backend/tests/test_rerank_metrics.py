from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[3]


def test_pair_labels_are_separate_and_ungraded_ndcg_null():
    from app.services.evaluation.benchmark.reranking import load_pair_references,evaluate_rerank_records
    dataset=load_pair_references(ROOT/'fixtures/rerank_benchmark/v1')
    assert len(dataset.input_pairs)>=12
    assert len({p.criterion.criterion_id for p in dataset.input_pairs})>=12
    assert all('design_label' not in p.model_dump() for p in dataset.input_pairs)
    report=evaluate_rerank_records(dataset,[],seed=1)
    assert report['ndcg_at_4'] is None and report['completed_records']==0
    assert report['false_exclusion_rate'] is None


def test_pair_input_hash_rejects_mutation(tmp_path):
    import shutil,json
    from app.services.evaluation.benchmark.reranking import load_pair_references
    shutil.copytree(ROOT/'fixtures/rerank_benchmark/v1',tmp_path/'pairs')
    target=tmp_path/'pairs'/'pairs.json'
    target.write_text(target.read_text()+' ')
    with pytest.raises(ValueError,match='HASH'):load_pair_references(tmp_path/'pairs')


def test_design_references_distinguish_negation_from_skill_mentions():
    from app.services.evaluation.benchmark.reranking import load_pair_references
    dataset=load_pair_references(ROOT/'fixtures/rerank_benchmark/v1')
    for i in range(12):
        assert dataset.design_labels[f'pair-{i:02}-1']=='limiting_evidence'
        assert dataset.design_labels[f'pair-{i:02}-2']=='mention_only'
        assert dataset.sufficient_groups[f'skill_{i:02}']==((f'pair-{i:02}-0',),)
    assert len(dataset.limiting_pair_ids)==12


def test_per_criterion_record_uses_only_its_own_reference_scope():
    from app.services.evaluation.benchmark.reranking import load_pair_references,evaluate_rerank_records
    dataset=load_pair_references(ROOT/'fixtures/rerank_benchmark/v1')
    ids=[f'pair-00-{i}' for i in range(5)]
    record={'case_id':'one','status':'ok','input_pair_ids':ids,'ranked_pair_ids':ids,
            'selected_pair_ids':ids[:4],'baseline_coverage':1.0}
    report=evaluate_rerank_records(dataset,[record],seed=1)
    for metric in ('limiting_retention','contradictory_group_retention','recall_at_5','recall_at_10','sufficient_group_delivery'):
        assert report[metric]==1.0,metric
    assert report['false_exclusion_rate']==0.0
    with pytest.raises(ValueError,match='SCOPE'):
        evaluate_rerank_records(dataset,[{**record,'selected_pair_ids':['pair-01-0']}],seed=1)
