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
