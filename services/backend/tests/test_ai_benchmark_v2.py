"""Frozen challenge data must retain correct scores/citations under long context."""
from pathlib import Path
import hashlib
import json
import pytest
from app.services.evaluation.benchmark.dataset import load_inputs,load_references,canonical_case
from app.services.embedding import build_chunks_from_spans

BASE=Path(__file__).resolve().parents[3]/'fixtures/ai_benchmark'


def test_v2_is_disjoint_and_does_not_rewrite_v1():
    assert hashlib.sha256((BASE/'v1/manifest.json').read_bytes()).hexdigest()=='55bc89a5c94022b7312a1dd56703a215ac1974f873cf177d5e4a6b3f9b62515a'
    old=load_inputs(BASE/'v1');new=load_inputs(BASE/'v2')
    assert {c.case_id for c in old.cases}.isdisjoint(c.case_id for c in new.cases)
    assert {canonical_case(c)[0] for c in old.cases}.isdisjoint(canonical_case(c)[0] for c in new.cases)
    assert old.roles==new.roles
    assert new.manifest_hash!=old.manifest_hash


def test_v2_long_projects_compete_for_bounded_pack():
    inputs=load_inputs(BASE/'v2')
    for case in inputs.cases:
        _,text,spans=canonical_case(case)
        chunks=build_chunks_from_spans(spans,lambda t:len(t.split()))
        assert len(text)>24000
        assert len(chunks)>10  # whitespace tokenizer is a conservative structural proxy, not a ranking metric
        assert 'project-competition' in case.scenario_tags
        assert len({s.span_id for s in spans})==len(spans)
        assert all(text[s.start_cp:s.end_cp]==s.text for s in spans)


def test_v2_references_remain_exact_with_anchor_null_conflict_cases():
    inputs=load_inputs(BASE/'v2');refs=load_references(BASE/'v2',inputs)
    assert len(refs)==60
    assert refs['v2-node-01'].criteria['backend_implementation'].score==0
    assert refs['v2-node-04'].criteria['backend_implementation'].score==3
    assert refs['v2-node-06'].criteria['backend_implementation'].score is None
    assert refs['v2-node-07'].criteria['backend_implementation'].status=='insufficient_evidence'
    assert refs['v2-node-08'].criteria['backend_implementation'].status=='insufficient_evidence'
    assert refs['v2-node-10'].criteria['backend_implementation'].status=='conflicting_evidence'
    for role in inputs.roles:
        cases=[c for c in inputs.cases if c.role_family==role]
        scores={r.score for c in cases for r in refs[c.case_id].criteria.values() if r.score is not None}
        assert scores=={0,1,2,3,4}
        assert any(r.status=='conflicting_evidence' for c in cases for r in refs[c.case_id].criteria.values())
    for case in inputs.cases:
        _,text,spans=canonical_case(case);registry={s.span_id:s for s in spans}
        for r in refs[case.case_id].criteria.values():
            for group in r.sufficient_evidence_groups:
                assert all(registry[e.span_id].text==e.quote for e in group)
                if r.status=='conflicting_evidence':
                    positions=[registry[e.span_id].start_cp for e in group]
                    assert max(positions)-min(positions)>5000


def test_v2_buried_evidence_exceeds_full_text_ceiling():
    inputs=load_inputs(BASE/'v2');refs=load_references(BASE/'v2',inputs)
    case=next(c for c in inputs.cases if c.case_id=='v2-node-13')
    registry={s.span_id:s for s in canonical_case(case)[2]}
    ref=refs[case.case_id].criteria['backend_implementation']
    assert ref.status=='assessed' and ref.score==3
    assert all(registry[e.span_id].start_cp>24000 for g in ref.sufficient_evidence_groups for e in g)
    pairs=[next(c for c in inputs.cases if c.case_id=='v2-node-'+n) for n in ('11','12')]
    assert pairs[0].cluster_id==pairs[1].cluster_id
    assert canonical_case(pairs[0])[1]==canonical_case(pairs[1])[1]
