"""DeepSeek Rate card pricing models and cost calculator.
Invariant: Rate card versions are immutable, explicit, and verified.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

RATE_CARD_VERSION = "deepseek-2024-11"

# Prices per 1,000,000 tokens in USD
RATE_CARD_PRICING = {
    "deepseek-chat": {
        "input_cache_miss_per_million": Decimal("0.14"),
        "input_cache_hit_per_million": Decimal("0.014"),
        "output_per_million": Decimal("0.28"),
    },
    "mock": {
        "input_cache_miss_per_million": Decimal("0.00"),
        "input_cache_hit_per_million": Decimal("0.00"),
        "output_per_million": Decimal("0.00"),
    },
}


def estimate_request_cost(
    input_tokens: int,
    max_output_tokens: int,
    model: str = "deepseek-chat",
) -> Decimal:
    """Calculate upper-bound estimated cost in USD for budget reservation (assuming cache miss)."""
    pricing = RATE_CARD_PRICING.get(model, RATE_CARD_PRICING["deepseek-chat"])

    input_cost = (Decimal(input_tokens) / Decimal(1_000_000)) * pricing["input_cache_miss_per_million"]
    output_cost = (Decimal(max_output_tokens) / Decimal(1_000_000)) * pricing["output_per_million"]

    return (input_cost + output_cost).quantize(Decimal("0.00000001"))


def calculate_actual_cost(
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    model: str = "deepseek-chat",
) -> Decimal:
    """Calculate precise actual cost in USD based on provider reported usage."""
    pricing = RATE_CARD_PRICING.get(model, RATE_CARD_PRICING["deepseek-chat"])

    miss_tokens = max(0, input_tokens - cached_input_tokens)
    miss_cost = (Decimal(miss_tokens) / Decimal(1_000_000)) * pricing["input_cache_miss_per_million"]
    hit_cost = (Decimal(cached_input_tokens) / Decimal(1_000_000)) * pricing["input_cache_hit_per_million"]
    out_cost = (Decimal(output_tokens) / Decimal(1_000_000)) * pricing["output_per_million"]

    return (miss_cost + hit_cost + out_cost).quantize(Decimal("0.00000001"))
