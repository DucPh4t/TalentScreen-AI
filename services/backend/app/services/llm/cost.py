"""DeepSeek Rate card pricing models and cost calculator.
Invariant: Rate card versions are immutable, explicit, and verified.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

RATE_CARD_VERSION = "deepseek-2026-09-26-peak"

# Prices per 1,000,000 tokens in USD
RATE_CARD_PRICING = {
    # Published peak prices. Billing may be lower off-peak; using peak
    # prices keeps reservations conservative. Recheck before each pilot.
    "deepseek-flash": {
        "input_cache_miss_per_million": Decimal("0.30"),
        "input_cache_hit_per_million": Decimal("0.006"),
        "output_per_million": Decimal("1.20"),
    },
    "deepseek-v4-pro": {
        "input_cache_miss_per_million": Decimal("1.32"),
        "input_cache_hit_per_million": Decimal("0.044"),
        "output_per_million": Decimal("3.96"),
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
    model: str = "deepseek-flash",
) -> Decimal:
    """Calculate upper-bound estimated cost in USD for budget reservation (assuming cache miss)."""
    pricing = RATE_CARD_PRICING[model]

    input_cost = (Decimal(input_tokens) / Decimal(1_000_000)) * pricing["input_cache_miss_per_million"]
    output_cost = (Decimal(max_output_tokens) / Decimal(1_000_000)) * pricing["output_per_million"]

    return (input_cost + output_cost).quantize(Decimal("0.00000001"))


def calculate_actual_cost(
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    model: str = "deepseek-flash",
) -> Decimal:
    """Estimate peak-rate spend from reported usage; provider billing is authoritative."""
    pricing = RATE_CARD_PRICING[model]

    miss_tokens = max(0, input_tokens - cached_input_tokens)
    miss_cost = (Decimal(miss_tokens) / Decimal(1_000_000)) * pricing["input_cache_miss_per_million"]
    hit_cost = (Decimal(cached_input_tokens) / Decimal(1_000_000)) * pricing["input_cache_hit_per_million"]
    out_cost = (Decimal(output_tokens) / Decimal(1_000_000)) * pricing["output_per_million"]

    return (miss_cost + hit_cost + out_cost).quantize(Decimal("0.00000001"))


def estimate_jev_request_cost(input_tokens: int, price_per_million_usd: float) -> Decimal:
    """Conservative Jev reservation; Jev currently bills input tokens, not generated text."""
    if input_tokens < 0 or price_per_million_usd <= 0:
        raise ValueError("Jev cost estimate requires non-negative usage and a verified positive rate")
    return (
        Decimal(input_tokens) / Decimal(1_000_000) * Decimal(str(price_per_million_usd))
    ).quantize(Decimal("0.00000001"))


def calculate_jev_actual_cost(input_tokens: int, price_per_million_usd: float) -> Decimal:
    """Settle Jev using reported input-token usage and the configured verified rate."""
    return estimate_jev_request_cost(input_tokens, price_per_million_usd)
