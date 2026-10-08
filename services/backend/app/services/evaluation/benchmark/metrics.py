"""Evaluator-only reference access, explicit denominators and paired clusters."""
from __future__ import annotations
from collections import defaultdict,Counter
from itertools import combinations
import math
import random
from .contracts import MetricsReport
from app.services.evaluation.metrics import criterion_mae,quadratic_weighted_kappa,recall_at_k

def mean(values):return sum(values)/len(values) if values else None
def rate(n,d):return n/d if d else None
def percentile(values,p):
    if not values:return None
    ordered=sorted(values);idx=(len(ordered)-1)*p
    lower=math.floor(idx);upper=math.ceil(idx)
    return ordered[lower]+(ordered[upper]-ordered[lower])*(idx-lower)

def paired_cluster_interval(pairs,*,seed,samples=1000):
    if samples<1:raise ValueError('INVALID_BOOTSTRAP_SAMPLES')
    groups=defaultdict(list)
    for cluster,a,b in pairs:
        if not math.isfinite(a) or not math.isfinite(b):raise ValueError('INVALID_BOOTSTRAP_VALUE')
        groups[cluster].append(b-a)
    if len(groups)<2 or len({v for vals in groups.values() for v in vals})<2:return None
    rng=random.Random(seed);keys=sorted(groups);resampled=[]
    for _ in range(samples):
        deltas=[v for key in rng.choices(keys,k=len(keys)) for v in groups[key]]
        resampled.append(mean(deltas))
    return percentile(resampled,.025),percentile(resampled,.975)

def covered(ref,ids):
    available=set(ids)
    return any({e.span_id for e in group}<=available for group in ref.sufficient_evidence_groups)

def evaluate_records(inputs,references,manifest,records):
    if manifest.dataset_hash!=inputs.manifest_hash or manifest.dataset_files!=inputs.hashes:
        raise ValueError('REPORT_DATASET_MISMATCH')
    planned=set(manifest.selection.combinations)
    keys=[(r.case_id,r.profile) for r in records]
    if len(set(keys))!=len(keys):raise ValueError('DUPLICATE_RUN_RECORD')
    if set(keys)-planned:raise ValueError('REPORT_UNPLANNED_RECORD')
    cases={c.case_id:c for c in inputs.cases}
    case_rows=[];is_mock=manifest.mode=='contract_only'
    for row in records:
        case=cases[row.case_id];refs=references[row.case_id].criteria
        if row.status=='accepted' and set(row.criteria)!=set(refs):raise ValueError('REPORT_CRITERION_SET_MISMATCH')
        diag=row.diagnostics;ranked=diag.get('ranked_evidence',{});initial=diag.get('initial_evidence',{});final=diag.get('final_evidence',{})
        numeric=[];status_hits=0;null_expected=0;correct_null=0;false_zero=0;unsupported=0;conflicts=0;conflict_hits=0
        recall5=[];recall10=[];initial_groups=[];final_groups=[];recovered=0;citation_count=0;scope_violations=0
        annotated_citations=0;supported_citations=0;cited_groups=[]
        for c,ref in refs.items():
            observation=row.criteria.get(c)
            if observation and ref.annotation_complete and not is_mock:
                status_hits+=observation.status==ref.status
                if ref.score is not None and observation.score is not None:numeric.append((ref.score,observation.score))
                if ref.score is None:
                    null_expected+=1;correct_null+=observation.score is None and observation.status==ref.status
                    false_zero+=observation.score==0;unsupported+=observation.score is not None
                if ref.status=='conflicting_evidence':
                    conflicts+=1;conflict_hits+=observation.status==ref.status and observation.score is None
            if observation:
                citation_count+=len(observation.evidence_ids)
                scope_violations+=sum(e not in set(final[c]) for e in observation.evidence_ids) if final.get(c) is not None else 0
                if ref.annotation_complete and not is_mock:
                    relevant_ids={e.span_id for group in ref.sufficient_evidence_groups for e in group}
                    annotated_citations+=len(observation.evidence_ids)
                    supported_citations+=sum(e in relevant_ids for e in observation.evidence_ids)
                    if ref.sufficient_evidence_groups and observation.status in {'assessed','conflicting_evidence'}:
                        cited_groups.append(int(covered(ref,observation.evidence_ids)))
            if not ref.sufficient_evidence_groups:continue
            relevant={e.span_id for group in ref.sufficient_evidence_groups for e in group}
            pool=ranked.get(c)
            if pool is not None and row.profile!='full_text':
                flattened=list(dict.fromkeys(s for chunk in pool for s in chunk))
                recall5.append(recall_at_k(relevant,flattened,5));recall10.append(recall_at_k(relevant,flattened,10))
            if initial.get(c) is not None and final.get(c) is not None:
                before=covered(ref,initial[c]);after=covered(ref,final[c])
                initial_groups.append(int(before));final_groups.append(int(after));recovered+=after and not before
        case_rows.append({'case_id':row.case_id,'profile':row.profile,'cluster_id':case.cluster_id,
            'role_family':case.role_family,'language':case.language,'status':row.status,'numeric_pairs':numeric,
            'status_hits':status_hits,'criteria_count':len(refs),'mae':mean([abs(a-b) for a,b in numeric]),
            'status_agreement':rate(status_hits,len(refs)) if row.status=='accepted' and not is_mock else None,
            'null_expected':null_expected,'correct_null':correct_null,'false_zero':false_zero,'unsupported':unsupported,
            'conflicts':conflicts,'conflict_hits':conflict_hits,'recall5':recall5,'recall10':recall10,
            'initial_groups':initial_groups,'final_groups':final_groups,'recovered':recovered,
            'citation_count':citation_count,'scope_violations':scope_violations,
            'annotated_citations':annotated_citations,'supported_citations':supported_citations,'cited_groups':cited_groups,
            'context':diag.get('context'),'packing':diag.get('packing')})
    profiles={}
    for profile in manifest.selection.profiles:
        rows=[r for r in records if r.profile==profile];stats=[r for r in case_rows if r['profile']==profile]
        counts={s:sum(r.status==s for r in rows) for s in ('accepted','failed','skipped','interrupted')}
        planned_cases=[c for c,p in manifest.selection.combinations if p==profile]
        counts.update(planned=len(planned_cases),recorded=len(rows),attempted=sum(r.status!='skipped' for r in rows),missing=len(planned_cases)-len(rows))
        accepted=[r for r in stats if r['status']=='accepted']
        pairs=[pair for row in accepted for pair in row['numeric_pairs']]
        expected=[a for a,b in pairs];predicted=[b for a,b in pairs]
        accepted_d=sum(r['criteria_count'] for r in accepted);planned_d=sum(len(references[c].criteria) for c in planned_cases)
        null_d=sum(r['null_expected'] for r in accepted);conflict_d=sum(r['conflicts'] for r in accepted)
        quality={'measurement':'unmeasured_mock' if is_mock else 'synthetic_reference_only','numeric_pairs':len(pairs),
            'mae':criterion_mae(expected,predicted) if not is_mock else None,
            'quadratic_kappa':quadratic_weighted_kappa(expected,predicted) if not is_mock else None,
            'status_agreement_accepted':rate(sum(r['status_hits'] for r in accepted),accepted_d) if not is_mock else None,
            'status_agreement_all_planned':rate(sum(r['status_hits'] for r in accepted),planned_d) if not is_mock else None,
            'accepted_criterion_denominator':accepted_d,'planned_criterion_denominator':planned_d,
            'null_reference_denominator':null_d,'correct_abstention_rate':rate(sum(r['correct_null'] for r in accepted),null_d) if not is_mock else None,
            'false_zero_rate':rate(sum(r['false_zero'] for r in accepted),null_d) if not is_mock else None,
            'unsupported_score_rate':rate(sum(r['unsupported'] for r in accepted),null_d) if not is_mock else None,
            'conflict_denominator':conflict_d,'conflict_agreement':rate(sum(r['conflict_hits'] for r in accepted),conflict_d) if not is_mock else None}
        retrieval={'ranked_criteria':sum(len(r['recall5']) for r in stats),
            'span_recall_at_5':mean([v for r in stats for v in r['recall5']]),'span_recall_at_10':mean([v for r in stats for v in r['recall10']]),
            'group_denominator':sum(len(r['initial_groups']) for r in stats),'initial_group_coverage':mean([v for r in stats for v in r['initial_groups']]),
            'final_group_coverage':mean([v for r in stats for v in r['final_groups']]),'recovered_criteria':sum(r['recovered'] for r in stats),
            'scope_violations':sum(r['scope_violations'] for r in stats),'citation_denominator':sum(r['citation_count'] for r in stats),
            'annotated_citation_denominator':sum(r['annotated_citations'] for r in stats),
            'annotated_citation_precision':rate(sum(r['supported_citations'] for r in stats),sum(r['annotated_citations'] for r in stats)),
            'cited_group_denominator':sum(len(r['cited_groups']) for r in stats),
            'cited_group_coverage':mean([v for r in stats for v in r['cited_groups']])}
        counters={key:sum(r.diagnostics.get('counters',{}).get(key,0) for r in rows) for key in ('rejected_citations','normalized_criteria','schema_failures')}
        timings={stage:{'n':len(values),'p50_ms':percentile(values,.5),'p95_ms':percentile(values,.95)}
            for stage in ('indexing','retrieval','graph','validation_scoring','total')
            for values in [[r.diagnostics.get('stage_ms',{}).get(stage) for r in rows if r.diagnostics.get('stage_ms',{}).get(stage) is not None]]}
        profiles[profile]={'counts':counts,'quality':quality,'retrieval':retrieval,'prevalidation':counters,'timing':timings,
            'context':{'measured_runs':sum(r['context'] is not None for r in stats),
                'unmeasured_runs':sum(r['context'] is None for r in stats),
                'size_truncated_runs':sum(bool((r['context'] or {}).get('size_truncated')) for r in stats),
                'context_limit_runs':sum(bool((r['context'] or {}).get('context_limit')) for r in stats)},
            'queue_ms':None,'model_calls':sum(len(r.invocations) for r in rows),'tool_calls':sum(r.tool_execution_count for r in rows),
            'repair_calls':sum(r.repair_count for r in rows),'input_tokens':sum(i.input_tokens or 0 for r in rows for i in r.invocations),
            'input_usage_measured_calls':sum(i.input_tokens is not None for r in rows for i in r.invocations),
            'output_tokens':sum(i.output_tokens or 0 for r in rows for i in r.invocations),
            'cached_input_tokens':sum(i.cached_input_tokens or 0 for r in rows for i in r.invocations),
            'cache_usage_measured_calls':sum(i.cached_input_tokens is not None for r in rows for i in r.invocations),
            'estimated_peak_usd':str(sum((i.estimated_peak_usd or 0 for r in rows for i in r.invocations))),
            'unsettled_invocations':sum(i.estimated_peak_usd is None and i.status in {'reserved','admitted','outcome_unknown'} for r in rows for i in r.invocations)}
        clusters=defaultdict(list)
        for r in rows:
            if r.status=='accepted' and 'counterfactual' in cases[r.case_id].scenario_tags:clusters[cases[r.case_id].cluster_id].append(r)
        complete=[group for group in clusters.values() if len(group)==2]
        invariant=sum({c:(o.status,o.score) for c,o in g[0].criteria.items()}=={c:(o.status,o.score) for c,o in g[1].criteria.items()} for g in complete)
        profiles[profile]['counterfactual']={'complete_pairs':len(complete),'incomplete_pairs':sum(len(g)!=2 for g in clusters.values()),
            'invariance_rate':rate(invariant,len(complete)) if not is_mock else None}
    paired=[]
    for a,b in combinations(manifest.selection.profiles,2):
        ar={r['case_id']:r for r in case_rows if r['profile']==a and r['status']=='accepted'}
        br={r['case_id']:r for r in case_rows if r['profile']==b and r['status']=='accepted'}
        overlap=sorted(set(ar)&set(br))
        for metric in ('mae','status_agreement'):
            pairs=[(cases[c].cluster_id,ar[c][metric],br[c][metric]) for c in overlap if ar[c][metric] is not None and br[c][metric] is not None]
            paired.append({'a':a,'b':b,'metric':metric,'overlap_cases':len(overlap),'comparable_cases':len(pairs),
                'clusters':len({c for c,x,y in pairs}),'mean_delta_b_minus_a':mean([y-x for c,x,y in pairs]),
                'ci95':paired_cluster_interval(pairs,seed=manifest.selection.seed) if pairs else None,
                'bootstrap_samples':1000,'seed':manifest.selection.seed,'interpretation':'exploratory'})
    slices={field:{value:{p:{'accepted':sum(r['status']=='accepted' for r in case_rows if r[field]==value and r['profile']==p),
        'planned':sum(cases[c].__getattribute__(field)==value for c,profile in manifest.selection.combinations if profile==p),
        'numeric_pairs':sum(len(r['numeric_pairs']) for r in case_rows if r[field]==value and r['profile']==p)} for p in manifest.selection.profiles}
        for value in sorted({cases[c].__getattribute__(field) for c in manifest.selection.case_ids})} for field in ('role_family','language')}
    failures=tuple({'case_id':r.case_id,'profile':r.profile,'status':r.status,'code':r.error_code} for r in records if r.status!='accepted')
    integrity=[]
    missing=len(planned)-len(records)
    if manifest.status=='complete' and (missing or any(r.status!='accepted' for r in records)):
        integrity.append('COMPLETED_MANIFEST_RECORDS_MISMATCH')
    if manifest.status not in {'running'} and missing:integrity.append('FINAL_MANIFEST_RECORDS_MISSING')
    actual_counts={'planned':len(planned),**{s:sum(r.status==s for r in records) for s in ('accepted','failed','skipped','interrupted')}}
    if any(k in manifest.counts and manifest.counts[k]!=v for k,v in actual_counts.items()):
        integrity.append('MANIFEST_COUNTS_MISMATCH')
    return MetricsReport(experiment_id=manifest.experiment_id,status='partial' if integrity and manifest.status=='complete' else manifest.status,model_quality=manifest.model_quality,
        profiles=profiles,paired=tuple(paired),slices=slices,case_metrics=tuple(case_rows),failures=failures,provenance=manifest.provenance,
        financial=manifest.financial,journal={'planned':len(planned),'records':len(records),'missing_records':missing,
            'manifest_status':manifest.status,'integrity_errors':integrity})
