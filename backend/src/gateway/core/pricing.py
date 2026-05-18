from __future__ import annotations

from dataclasses import dataclass

# (provider, model) -> (input_per_M, output_per_M) USD per 1M tokens.
# List prices as of 2026-05; reviewer-friendly so cost calc is reproducible.
PRICE_TABLE: dict[tuple[str, str], tuple[float, float]] = {
    ("anthropic", "claude-sonnet-4-6"): (3.0, 15.0),
    ("anthropic", "claude-haiku-4-5"): (1.0, 5.0),
    ("openai", "gpt-4o-mini"): (0.15, 0.6),
    ("openai", "gpt-4o"): (2.5, 10.0),
    ("bedrock", "anthropic.claude-3-5-sonnet-20241022-v2:0"): (3.0, 15.0),
}


@dataclass(frozen=True)
class CostBreakdown:
    input_cost_usd: float
    output_cost_usd: float
    total_usd: float


def compute_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> CostBreakdown:
    rates = PRICE_TABLE.get((provider, model))
    if rates is None:
        return CostBreakdown(0.0, 0.0, 0.0)
    inp_rate, out_rate = rates
    inp = prompt_tokens / 1_000_000 * inp_rate
    out = completion_tokens / 1_000_000 * out_rate
    return CostBreakdown(round(inp, 6), round(out, 6), round(inp + out, 6))
