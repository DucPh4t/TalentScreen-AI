"""Offline planning: conservative all-call bounds, no provider call or download."""
from __future__ import annotations
import ast
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from app.config import get_settings
from app.services.assessment.policy import AssessmentExecutionPolicy
from app.services.llm.cost import RATE_CARD_VERSION,RATE_CARD_PRICING,estimate_request_cost
from .contracts import InputBound,BudgetPlan,BudgetCombination,DatasetInputs,RunSelection,ProfileName

TOKENIZER_SHA256='c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b'
ENCODING_SHA256='502bdaec8a3fd88ebc24c4721a7038fbe42f2063c664638127056107920035c1'
TOKENIZER_REVISION='2cba9e42aa026125f3ed06c6d98c1db82f7ca027'
PROOF_REFERENCE='docs/evaluation/deepseek-token-bound.json'
# Pinned official tokenizer_config.json model_max_length, pricing page confirms 1M.
MODEL_CONTEXT={'deepseek-flash':1048576,'mock':1048576}


def verify_utf8_artifacts(cache: Path) -> InputBound:
    """Inspect pinned JSON/AST only; never execute downloaded reference code."""
    for file,expected in (('tokenizer.json',TOKENIZER_SHA256),('encoding.py',ENCODING_SHA256)):
        path=cache/file
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('TOKENIZER_PROOF_UNAVAILABLE')
    tokenizer=json.loads((cache/'tokenizer.json').read_text())
    if (tokenizer['model']['type']!='BPE' or tokenizer['normalizer']!={'type':'Sequence','normalizers':[]}
        or tokenizer['post_processor']['type']!='ByteLevel'
        or any(not t.get('content') for t in tokenizer.get('added_tokens',[]))):
        raise ValueError('TOKENIZER_BYTE_BOUND_UNPROVEN')
    sequence=tokenizer['pre_tokenizer']['pretokenizers']
    if (sequence[-1]!={'type':'ByteLevel','add_prefix_space':False,'trim_offsets':True,'use_regex':False}
        or any(t.get('type')!='Split' or t.get('behavior')!='Isolated' or t.get('invert') for t in sequence[:-1])):
        raise ValueError('TOKENIZER_BYTE_BOUND_UNPROVEN')
    template=None
    for node in ast.parse((cache/'encoding.py').read_text()).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TOOLS_TEMPLATE' for t in node.targets):
            template=ast.literal_eval(node.value)
    if not isinstance(template,str):raise ValueError('TOKENIZER_FRAMING_UNPROVEN')
    skeleton=template.format(tool_schemas='',dsml_token='｜DSML｜',tc_block_name=' calls',tool_call_tag_name=' invoke',
                            tool_parameter_tag_name=' parameter',thinking_start_token='<think>',thinking_end_token='</think>')
    # Bounded grammar enforced on every request: <=8 messages, <=2 historical
    # tool calls, <=4 parameters and <=512 schema separators; all are text only.
    overhead=len(skeleton.encode())+512+8*96+4*120+2*120+2*96+2*32+256+64
    if overhead>4096:raise ValueError('TOKENIZER_FRAMING_UNPROVEN')
    return InputBound(strategy='verified_utf8',max_input_tokens=69632,max_serialized_bytes=65536,framing_allowance=4096,
        tokenizer_artifact_sha256=TOKENIZER_SHA256,proof_reference=PROOF_REFERENCE,rate_card_version=RATE_CARD_VERSION)


def context_bound(model: str) -> InputBound:
    if model not in MODEL_CONTEXT:raise ValueError('BENCHMARK_MODEL_UNVERIFIED')
    return InputBound(strategy='model_context',max_input_tokens=MODEL_CONTEXT[model],proof_reference=PROOF_REFERENCE,rate_card_version=RATE_CARD_VERSION)


def plan_budget(inputs: DatasetInputs,selection: RunSelection,policies: dict[ProfileName,AssessmentExecutionPolicy],
                *,model: str,cap_usd: Decimal,bound: InputBound) -> BudgetPlan:
    if model not in MODEL_CONTEXT or model not in RATE_CARD_PRICING or bound.rate_card_version!=RATE_CARD_VERSION:
        raise ValueError('BENCHMARK_MODEL_OR_RATE_UNVERIFIED')
    bound=InputBound.model_validate(bound.model_dump())
    if bound.strategy=='model_context' and bound.max_input_tokens!=MODEL_CONTEXT[model]:
        raise ValueError('INPUT_BOUND_UNVERIFIED')
    if bound.strategy=='verified_utf8' and bound.tokenizer_artifact_sha256!=TOKENIZER_SHA256:
        raise ValueError('INPUT_BOUND_UNVERIFIED')
    known={c.case_id for c in inputs.cases}
    if set(selection.case_ids)-known or set(selection.profiles)!=set(policies) or any(policies[p].profile!=p for p in policies):
        raise ValueError('BENCHMARK_SELECTION_POLICY_MISMATCH')
    cost=estimate_request_cost(bound.max_input_tokens,4096,model)*4
    combinations=tuple(BudgetCombination(case_id=c,profile=p,upper_usd=cost) for c,p in selection.combinations)
    total=sum((c.upper_usd for c in combinations),Decimal(0))
    return BudgetPlan(model=model,bound=bound,combinations=combinations,total_upper_usd=total,cap_usd=cap_usd,admitted=total<=cap_usd)


def embedding_cache_available() -> bool:
    from huggingface_hub import try_to_load_from_cache
    settings=get_settings()
    required=('config.json','tokenizer_config.json','tokenizer.json')
    def exists(file):
        value=try_to_load_from_cache(settings.EMBEDDING_MODEL,file,revision=settings.EMBEDDING_MODEL_REVISION)
        return isinstance(value,str) and Path(value).is_file()
    return all(exists(f) for f in required) and (exists('model.safetensors') or exists('pytorch_model.bin'))


def validate_live_preflight(plan: BudgetPlan,*,provider_host: str,pricing_verified_at: str,model_available_locally: bool) -> None:
    if not plan.admitted:raise ValueError('BENCHMARK_BUDGET_PLAN_REJECTED')
    if provider_host!='api.deepseek.com' or plan.model!='deepseek-flash':raise ValueError('BENCHMARK_PROVIDER_UNVERIFIED')
    try:age=(date.today()-date.fromisoformat(pricing_verified_at)).days
    except (TypeError,ValueError) as exc:raise ValueError('BENCHMARK_PRICING_UNVERIFIED') from exc
    if not 0<=age<=7:raise ValueError('BENCHMARK_PRICING_UNVERIFIED')
    if not model_available_locally:raise ValueError('BENCHMARK_E5_NOT_CACHED')

def resolve_cached_embedding_revision() -> str:
    """Resolve a mutable local alias once, then require files at its immutable SHA."""
    import re
    from huggingface_hub import try_to_load_from_cache
    settings=get_settings()
    if settings.EMBEDDING_MODEL!='intfloat/multilingual-e5-base':raise ValueError('BENCHMARK_E5_MODEL_UNVERIFIED')
    value=try_to_load_from_cache(settings.EMBEDDING_MODEL,'config.json',revision=settings.EMBEDDING_MODEL_REVISION)
    if not isinstance(value,str) or not Path(value).is_file():raise ValueError('BENCHMARK_E5_NOT_CACHED')
    snapshot=Path(value).parent;revision=snapshot.name
    if snapshot.parent.name!='snapshots' or not re.fullmatch('[0-9a-f]{40}',revision):raise ValueError('BENCHMARK_E5_REVISION_UNVERIFIED')
    def exists(file):
        item=try_to_load_from_cache(settings.EMBEDDING_MODEL,file,revision=revision)
        return isinstance(item,str) and Path(item).parent==snapshot and Path(item).is_file()
    if not all(exists(f) for f in ('config.json','tokenizer_config.json','tokenizer.json')) or not (exists('model.safetensors') or exists('pytorch_model.bin')):
        raise ValueError('BENCHMARK_E5_NOT_CACHED')
    return revision
