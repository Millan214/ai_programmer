"""Per-model USD pricing used to compute ``agent_turn.cost_usd``.

Phase 0 has no model router (that lands in Phase 2), so the table is deliberately
hardcoded. Numbers are per 1M tokens; unknown models return ``None`` so the row still
persists but doesn't claim a bogus cost.
"""

from decimal import Decimal

# (input_per_million, output_per_million) — Claude 4.x public pricing tiers.
_PRICING: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-4-7": (Decimal("15"), Decimal("75")),
    "claude-opus-4-8": (Decimal("15"), Decimal("75")),
    "claude-sonnet-4-6": (Decimal("3"), Decimal("15")),
    "claude-haiku-4-5-20251001": (Decimal("1"), Decimal("5")),
    "claude-fable-5": (Decimal("15"), Decimal("75")),
}

_PER_MILLION = Decimal(1_000_000)


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    if model not in _PRICING:
        return None
    input_rate, output_rate = _PRICING[model]
    return (
        input_rate * Decimal(input_tokens) + output_rate * Decimal(output_tokens)
    ) / _PER_MILLION
