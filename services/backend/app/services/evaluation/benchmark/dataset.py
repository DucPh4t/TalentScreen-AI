"""Frozen dataset validation; labels are loaded separately from runner inputs."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import uuid
from .contracts import CaseInput, CaseReference, DatasetInputs, ProfileName, PROFILES, RoleInput, RunSelection
from app.services.sanitizer import sanitize_text, build_source_spans_from_canonical

NAMESPACE = uuid.UUID('1d542c93-3aa8-4b5a-b348-02653a748d22')
FILES = ('cases.jsonl', 'roles.json', 'references.jsonl')

def _safe_file(root: Path, name: str) -> Path:
    p = root / name
    if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(root.resolve()):
        raise ValueError('DATASET_PATH_INVALID')
    return p

def _validate_hashes(root: Path) -> tuple[dict, str]:
    manifest_bytes = _safe_file(root, 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get('schema_version') != 'ai-benchmark.v1' or set(manifest.get('files', {})) != set(FILES):
        raise ValueError('DATASET_MANIFEST_INVALID')
    for name in FILES:
        if hashlib.sha256(_safe_file(root, name).read_bytes()).hexdigest() != manifest['files'][name]:
            raise ValueError('DATASET_HASH_MISMATCH')
    return manifest, hashlib.sha256(manifest_bytes).hexdigest()

def canonical_case(case: CaseInput):
    version_id = uuid.uuid5(NAMESPACE, 'ai-benchmark.v1/' + case.case_id)
    canonical, _, _ = sanitize_text(case.cv_text)
    return version_id, canonical, build_source_spans_from_canonical(version_id, canonical)

def load_inputs(root: Path) -> DatasetInputs:
    root = root.resolve()
    manifest, manifest_hash = _validate_hashes(root)
    cases = tuple(CaseInput.model_validate(json.loads(line)) for line in _safe_file(root, 'cases.jsonl').read_text().splitlines() if line.strip())
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError('DUPLICATE_CASE')
    roles = {k: RoleInput.model_validate(v) for k, v in json.loads(_safe_file(root, 'roles.json').read_text()).items()}
    if len(cases) != 60 or Counter(c.role_family for c in cases) != {'backend_node':20, 'ai_ml':20, 'android':20}:
        raise ValueError('DATASET_SHAPE_INVALID')
    clusters: dict[str, set[str]] = {}
    for c in cases:
        if c.role_family not in roles or c.jd_ref != c.role_family or c.rubric_ref != c.role_family:
            raise ValueError('UNKNOWN_ROLE_REFERENCE')
        clusters.setdefault(c.cluster_id, set()).add(c.split)
    if any(len(splits) != 1 for splits in clusters.values()):
        raise ValueError('CLUSTER_SPLIT_LEAK')
    for role in roles:
        rows = [c for c in cases if c.role_family == role]
        if Counter(c.language for c in rows) != {'vi':7, 'en':7, 'mixed':6} or Counter(c.split for c in rows) != {'development':12, 'public_test':8}:
            raise ValueError('DATASET_DISTRIBUTION_INVALID')
        if any({c.language for c in rows if c.split == split} != {'vi','en','mixed'} for split in ('development','public_test')):
            raise ValueError('DATASET_LANGUAGE_COVERAGE_INVALID')
    return DatasetInputs(root=root, cases=cases, roles=roles, hashes=manifest['files'], manifest_hash=manifest_hash)

def load_references(root: Path, inputs: DatasetInputs) -> dict[str, CaseReference]:
    _validate_hashes(root)
    rows = [CaseReference.model_validate(json.loads(line)) for line in _safe_file(root, 'references.jsonl').read_text().splitlines() if line.strip()]
    refs = {r.case_id:r for r in rows}
    if len(refs) != len(rows) or set(refs) != {c.case_id for c in inputs.cases}:
        raise ValueError('GOLD_CASE_SET_INVALID')
    for case in inputs.cases:
        gold = refs[case.case_id]
        if set(gold.criteria) != {c.id for c in inputs.roles[case.role_family].criteria}:
            raise ValueError('GOLD_CRITERION_SET_INVALID')
        registry = {s.span_id:s for s in canonical_case(case)[2]}
        for ref in gold.criteria.values():
            for group in ref.sufficient_evidence_groups:
                if any(e.span_id not in registry or registry[e.span_id].text != e.quote for e in group):
                    raise ValueError('GOLD_SPAN_INVALID')
    return refs

def select_runs(inputs: DatasetInputs, *, split: str | None, case_ids: tuple[str,...], profiles: tuple[ProfileName,...], seed: int) -> RunSelection:
    if not profiles or len(set(profiles)) != len(profiles) or set(profiles) - set(PROFILES):
        raise ValueError('INVALID_PROFILES')
    if case_ids and split is not None:
        raise ValueError('SELECTION_CONFLICT')
    if split not in (None, 'development', 'public_test', 'all'):
        raise ValueError('INVALID_SPLIT')
    known = {c.case_id for c in inputs.cases}
    if len(set(case_ids)) != len(case_ids) or set(case_ids) - known:
        raise ValueError('UNKNOWN_CASE')
    selected = case_ids or tuple(c.case_id for c in inputs.cases if split in (None, 'all', c.split))
    rng = random.Random(seed)
    pairs = []
    for case_id in selected:
        order = list(profiles)
        rng.shuffle(order)
        pairs.extend((case_id, profile) for profile in order)
    return RunSelection(case_ids=selected, profiles=profiles, combinations=tuple(pairs), seed=seed)
