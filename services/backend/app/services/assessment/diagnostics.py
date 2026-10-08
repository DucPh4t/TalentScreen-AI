"""Run-local allowlisted measurements. Never retain raw CV/model/error content."""
from __future__ import annotations
from contextlib import contextmanager
import copy
from functools import wraps
import json
import math
import re
import time
from typing import Any
from pydantic import ValidationError
from app.schemas.assessment import AssessmentOutputSchema

STAGES=frozenset({'indexing','retrieval','graph','validation_scoring','total'})
SPAN=re.compile(r'^spn_[0-9a-f]{24}$')
CRITERION=re.compile(r'^[a-z][a-z0-9_]{1,49}$')

class AssessmentDiagnostics:
    def __init__(self,criterion_ids: set[str]):
        self.criteria=frozenset(c for c in criterion_ids if isinstance(c,str) and CRITERION.fullmatch(c))
        self.stages={name:None for name in sorted(STAGES)}
        self.ranked={c:None for c in sorted(self.criteria)}
        self.initial={c:[] for c in sorted(self.criteria)}
        self.final={c:[] for c in sorted(self.criteria)}
        self.counters={'rejected_citations':0,'normalized_criteria':0,'schema_failures':0}

    @staticmethod
    def _spans(value):
        if not isinstance(value,(list,tuple,set)):return []
        return list(dict.fromkeys(s for s in value if isinstance(s,str) and SPAN.fullmatch(s)))

    def record_stage(self,name: str,elapsed_ms: float) -> None:
        if name not in STAGES or isinstance(elapsed_ms,bool) or not isinstance(elapsed_ms,(int,float)):
            return
        if not math.isfinite(elapsed_ms) or elapsed_ms<0:return
        self.stages[name]=round((self.stages[name] or 0)+elapsed_ms,4)

    def record_retrieval(self,criterion_id: str,ranked_chunks: list[list[str]],delivered_span_ids: list[str]) -> None:
        if criterion_id not in self.criteria or not isinstance(ranked_chunks,list):return
        self.ranked[criterion_id]=[self._spans(chunk) for chunk in ranked_chunks[:10]]
        self.initial[criterion_id]=self._spans(delivered_span_ids)

    def record_initial_evidence(self,mapping: dict[str,list[str]]) -> None:
        if isinstance(mapping,dict):
            self.initial={c:self._spans(mapping.get(c,[])) for c in sorted(self.criteria)}

    def record_final_evidence(self,mapping: dict[str,list[str]]) -> None:
        if isinstance(mapping,dict):
            self.final={c:self._spans(mapping.get(c,[])) for c in sorted(self.criteria)}

    def record_validation(self,*,rejected_citations: int,normalized_criteria: int,schema_failures: int) -> None:
        for name,value in (('rejected_citations',rejected_citations),('normalized_criteria',normalized_criteria),('schema_failures',schema_failures)):
            if type(value) is int and value>=0:self.counters[name]+=value

    def snapshot(self) -> dict[str,Any]:
        return copy.deepcopy({'stage_ms':self.stages,'ranked_evidence':self.ranked,'initial_evidence':self.initial,
                              'final_evidence':self.final,'counters':self.counters})


def safe_record(recorder,method: str,*args,**kwargs):
    if recorder is None:return
    try:getattr(recorder,method)(*args,**kwargs)
    except Exception:pass  # Optional instrumentation cannot change business outcomes.

@contextmanager
def measure_stage(recorder,name: str):
    start=time.perf_counter()
    try:yield
    finally:safe_record(recorder,'record_stage',name,(time.perf_counter()-start)*1000)


def measured(stage: str):
    def decorate(fn):
        @wraps(fn)
        async def wrapped(*args,**kwargs):
            with measure_stage(kwargs.get('diagnostics'),stage):
                return await fn(*args,**kwargs)
        return wrapped
    return decorate


def inspect_raw_output(raw: str,registry: dict,allowed: dict[str,set[str]],expected_ids: set[str]) -> dict[str,int]:
    counts={'rejected_citations':0,'normalized_criteria':0,'schema_failures':0}
    try:
        parsed=json.loads(raw)
        try:
            dto=AssessmentOutputSchema.model_validate(parsed)
            if {c.criterion_id for c in dto.criteria}!=expected_ids:counts['schema_failures']=1
        except (ValidationError,TypeError,ValueError):counts['schema_failures']=1
        if not isinstance(parsed,dict) or not isinstance(parsed.get('criteria'),list):return counts
        for item in parsed['criteria']:
            if not isinstance(item,dict):continue
            criterion_id=item.get('criterion_id')
            if not isinstance(criterion_id,str) or criterion_id not in expected_ids:continue
            evidence=item.get('evidence')
            if not allowed.get(criterion_id) and (item.get('score') is not None or item.get('status')!='insufficient_evidence' or evidence):
                counts['normalized_criteria']+=1
            if not isinstance(evidence,list):continue
            for e in evidence:
                if not isinstance(e,dict):counts['rejected_citations']+=1;continue
                span_id=e.get('span_id')
                span=registry.get(span_id) if isinstance(span_id,str) else None
                if span is None or span_id not in allowed.get(criterion_id,set()) or e.get('quote')!=span.text:
                    counts['rejected_citations']+=1
    except (json.JSONDecodeError,TypeError,ValueError):counts['schema_failures']=1
    return counts
