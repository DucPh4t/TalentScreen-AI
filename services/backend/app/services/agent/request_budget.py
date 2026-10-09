"""Fit complete canonical requests by removing whole evidence spans, never quotes."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import replace
import json
from app.services.llm.types import CompletionRequest

REQUEST_BYTE_LIMIT = 65_536
REQUEST_PACKING_VERSION = 'serialized-evidence-v1'


class RequestBudgetError(ValueError):
    pass


def serialized_bytes(request: CompletionRequest) -> int:
    # This canonical representation includes null optional fields; it bounds the
    # equivalent compact HTTP payload, which omits those fields.
    from app.services.llm.orchestrator import _serialized_request_payload
    return len(_serialized_request_payload(request).encode('utf-8'))


def fit_evidence_request(request: CompletionRequest, priority_span_ids: list[str], *,
                         byte_limit: int = REQUEST_BYTE_LIMIT, max_evidence_chars: int = 24000):
    """Retain a priority prefix; remove IDs and full quotes from every evidence message.

    Tool-call IDs/arguments, system rules and rubric definitions are not shortened.
    JSON whitespace is compacted without changing values. The input is never mutated.
    """
    if type(byte_limit) is not int or byte_limit <= 0 or type(max_evidence_chars) is not int or max_evidence_chars < 0:
        raise RequestBudgetError('ASSESSMENT_REQUEST_BUDGET_INVALID')
    messages = deepcopy(request.messages or [
        {'role': 'system', 'content': request.system_prompt},
        {'role': 'user', 'content': request.user_prompt}])
    structures = {}
    for index, message in enumerate(messages):
        if message.get('role') not in {'user', 'tool'} or not isinstance(message.get('content'), str):
            continue
        try:
            value = json.loads(message['content'])
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            structures[index] = value
    removed = []
    priorities = list(dict.fromkeys(priority_span_ids))
    original_bytes = serialized_bytes(request)

    def materialize():
        result = deepcopy(messages)
        omitted = set(removed)
        for index, original in structures.items():
            value = deepcopy(original)
            if isinstance(value.get('source_spans'), list):
                value['source_spans'] = [span for span in value['source_spans']
                    if not isinstance(span, dict) or span.get('span_id') not in omitted]
            mapping = value.get('retrieved_evidence_by_criterion')
            if isinstance(mapping, dict):
                value['retrieved_evidence_by_criterion'] = {
                    key: [s for s in ids if s not in omitted] for key, ids in mapping.items()}
            result[index]['content'] = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        return replace(request, messages=result)

    def evidence_characters():
        quotes = {}
        for value in structures.values():
            for span in value.get('source_spans', []):
                if isinstance(span, dict) and isinstance(span.get('quote'), str) and span.get('span_id') not in removed:
                    quotes[span['span_id']] = span['quote']
        return sum(len(quote) for quote in quotes.values())

    fitted = materialize()
    while (serialized_bytes(fitted) > byte_limit or evidence_characters() > max_evidence_chars) and priorities:
        removed.append(priorities.pop())
        fitted = materialize()
    if serialized_bytes(fitted) > byte_limit or evidence_characters() > max_evidence_chars:
        raise RequestBudgetError('ASSESSMENT_REQUEST_OVERHEAD_LIMIT')
    return fitted, removed, {'original_bytes': original_bytes, 'serialized_bytes': serialized_bytes(fitted),
        'byte_limit': byte_limit, 'excluded_span_count': len(removed),
        'evidence_characters': evidence_characters(), 'character_limit': max_evidence_chars}
