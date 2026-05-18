from __future__ import annotations

from gateway.core.pricing import compute_cost


def test_known_pair_priced() -> None:
    c = compute_cost("openai", "gpt-4o-mini", 1_000_000, 1_000_000)
    # gpt-4o-mini: 0.15 in / 0.60 out per million.
    assert abs(c.input_cost_usd - 0.15) < 1e-6
    assert abs(c.output_cost_usd - 0.60) < 1e-6
    assert abs(c.total_usd - 0.75) < 1e-6


def test_unknown_pair_priced_zero() -> None:
    c = compute_cost("unknown", "model-xyz", 1000, 1000)
    assert c.total_usd == 0.0


def test_monotone_in_tokens() -> None:
    small = compute_cost("anthropic", "claude-sonnet-4-6", 100, 100)
    big = compute_cost("anthropic", "claude-sonnet-4-6", 10000, 10000)
    assert big.total_usd > small.total_usd


def test_output_priced_higher_than_input_for_claude_sonnet() -> None:
    c = compute_cost("anthropic", "claude-sonnet-4-6", 1000, 1000)
    assert c.output_cost_usd > c.input_cost_usd
