#!/usr/bin/env python3
"""Build a new, frozen synthetic collection; never overwrite an existing dataset.

Wire schema remains v1. V2-prefixed IDs retain canonical citation compatibility
while keeping source UUIDs disjoint. This authoring tool is never a runner input.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services/backend'))
from app.services.evaluation.benchmark.dataset import load_inputs, load_references, canonical_case


def archived_project(role, language, project_no):
    """Keyword-rich team plans explicitly exclude individual implementation evidence."""
    criterion = role.criteria[(project_no - 1) % len(role.criteria)]
    language_key = 'en' if language == 'en' else 'vi'
    task = criterion.bilingual_terms[language_key][0]
    if language_key == 'en':
        title = f'ARCHIVE PROJECT {project_no:02d}: planned {task}'
        paragraph = (
            f'The team planning document listed {task} as a proposed scope for this archived project. '
            'My responsibility was to take meeting notes, maintain the dependency register and arrange review sessions; '
            'I did not implement or test this component and no individual technical result is claimed here. '
            f'The proposed acceptance checklist mentioned {task}, but implementation belonged to another team member. '
            'The planning notes describe rollback risks, integration dependencies, error-path discussions, staging access '
            'and a future verification meeting; these are unexecuted plans rather than completed personal work. '
            'No benchmark, test report, measured performance improvement or independently delivered code is attributed to me. '
        )
    else:
        title = f'DỰ ÁN LƯU TRỮ {project_no:02d}: dự kiến {task}'
        paragraph = (
            f'Bản kế hoạch nhóm liệt kê việc {task} trong phạm vi dự kiến của dự án lưu trữ này. '
            'Phần việc của tôi là ghi biên bản họp, cập nhật danh sách phụ thuộc và sắp xếp buổi rà soát; '
            'tôi không triển khai hoặc kiểm thử thành phần này và không khẳng định kết quả kỹ thuật cá nhân ở đây. '
            f'Danh sách nghiệm thu dự kiến nhắc tới việc {task}, nhưng phần triển khai thuộc thành viên khác. '
            'Biên bản trao đổi rủi ro hoàn tác, phụ thuộc tích hợp, đường đi lỗi, quyền môi trường thử nghiệm '
            'và lịch xác minh trong tương lai; đây là kế hoạch chưa thực hiện, không phải công việc cá nhân đã hoàn thành. '
            'Không có báo cáo kiểm thử, số đo hiệu năng, cải tiến sau đo đạc hoặc mã nguồn tự bàn giao được gán cho tôi. '
        )
    return title + '\n' + paragraph * 2


def build_collection(output):
    output = Path(output)
    if output.exists() or output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError('DATASET_OUTPUT_EXISTS_OR_UNSAFE')
    source = ROOT / 'fixtures/ai_benchmark/v1'
    inputs = load_inputs(source)
    refs = load_references(source, inputs)
    old = {case.case_id: case for case in inputs.cases}
    cases = []
    references = []
    for case in inputs.cases:
        number = int(case.case_id.rsplit('-', 1)[1])
        # Identity-counterfactual members must retain identical technical text.
        template = old[case.case_id.rsplit('-', 1)[0] + '-11'] if number == 12 else case
        effective_number = 11 if number == 12 else number
        lines = template.cv_text.splitlines()
        header = '\n'.join(case.cv_text.splitlines()[:2] + lines[2:3])
        body = '\n'.join(lines[3:])
        deferred = []
        has_conflict = any(ref.status == 'conflicting_evidence' for ref in refs[case.case_id].criteria.values())
        if has_conflict:
            for ref in refs[case.case_id].criteria.values():
                if ref.status == 'conflicting_evidence':
                    # Place the disavowal far from the original claim so an incomplete
                    # pack can expose only one side; gold still requires both spans.
                    for group in ref.sufficient_evidence_groups:
                        for evidence in group[1:]:
                            if evidence.quote not in deferred:
                                body = body.replace(evidence.quote, '')
                                deferred.append(evidence.quote)
        gallery = '\n\n'.join(archived_project(inputs.roles[case.role_family], template.language, n) for n in range(1, 31))
        if not has_conflict and (effective_number % 2 or 'buried-evidence' in case.scenario_tags):
            text = header + '\nPROJECT ARCHIVE\n' + gallery + '\nTECHNICAL CONTRIBUTIONS\n' + body
        else:
            text = header + '\nTECHNICAL CONTRIBUTIONS\n' + body + '\nPROJECT ARCHIVE\n' + gallery
        if deferred:
            text += '\nROLE CLARIFICATION AFTER PROJECT ARCHIVE\n' + '\n'.join(deferred)
        new_case = case.model_copy(update={'case_id': 'v2-' + case.case_id, 'cluster_id': 'v2-' + case.cluster_id,
            'cv_text': text, 'scenario_tags': (*case.scenario_tags, 'long-context', 'project-competition')})
        registry = canonical_case(new_case)[2]
        def relocate(evidence):
            matches = [span for span in registry if span.text == evidence.quote]
            if len(matches) != 1:
                raise ValueError('V2_REFERENCE_AMBIGUOUS')
            return evidence.model_copy(update={'span_id': matches[0].span_id})
        gold = refs[case.case_id].model_copy(update={'case_id': new_case.case_id, 'criteria': {
            key: ref.model_copy(update={'sufficient_evidence_groups': tuple(tuple(relocate(e) for e in group)
                for group in ref.sufficient_evidence_groups)}) for key, ref in refs[case.case_id].criteria.items()}})
        cases.append(new_case)
        references.append(gold)
    output.mkdir(parents=True)
    (output / 'cases.jsonl').write_text(''.join(c.model_dump_json() + '\n' for c in cases))
    (output / 'references.jsonl').write_text(''.join(r.model_dump_json() + '\n' for r in references))
    (output / 'roles.json').write_bytes((source / 'roles.json').read_bytes())
    manifest = {
        'schema_version': 'ai-benchmark.v1', 'dataset_revision': 'v2', 'data_origin': 'synthetic',
        'labels_origin': 'design_expected', 'seed': 20261009, 'public_test_is_protected_holdout': False,
        'annotation_method': 'Frozen v1 design expectations relocated exactly; no independent HR labels',
        'generation': {'builder': 'scripts/build_ai_benchmark_v2.py',
            'builder_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'source_v1_manifest_sha256': inputs.manifest_hash, 'archived_projects_per_cv': 30},
        'frozen_before_retrieval_measurement': True,
        'files': {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                  for name in ('cases.jsonl', 'roles.json', 'references.jsonl')},
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    # Authoring validates labels offline; neither runner nor model receives them.
    result = load_inputs(output)
    load_references(output, result)
    return {'cases': len(result.cases), 'dataset_hash': result.manifest_hash, 'origin': 'synthetic_design_expected'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'fixtures/ai_benchmark/v2')
    args = parser.parse_args()
    print(json.dumps(build_collection(args.output)))


if __name__ == '__main__':
    main()
