"""Enqueue-time policy freezing; missing historical fields preserve off behavior."""
from app.config import Settings
from .contracts import RerankPolicy


def freeze_rerank_policy(settings: Settings)->RerankPolicy:
    if settings.JEV_RERANK_MODE=='off':return RerankPolicy()
    # Revalidate mutable Settings instances as well as startup input.
    Settings.model_validate(settings.model_dump())
    return RerankPolicy(mode=settings.JEV_RERANK_MODE,requested_model=settings.JEV_MODEL,
        accepted_models=tuple(settings.JEV_RERANK_ACCEPTED_MODELS),endpoint=settings.JEV_BASE_URL,
        rate_per_million_usd=settings.JEV_INPUT_PRICE_PER_MILLION_USD,
        rate_verified_at=settings.JEV_RATE_CARD_VERIFIED_AT)


def load_rerank_policy(snapshot: dict)->RerankPolicy:
    raw=snapshot.get('reranking_policy')
    digest=snapshot.get('reranking_policy_hash')
    if raw is None and digest is None:return RerankPolicy()
    try:
        p=RerankPolicy.model_validate(raw)
        if p.digest!=digest:raise ValueError('digest')
        return p
    except (ValueError,TypeError) as exc:
        raise ValueError('RERANK_POLICY_INVALID') from exc
