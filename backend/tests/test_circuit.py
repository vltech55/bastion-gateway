from __future__ import annotations

import time

import pytest

from gateway.routing.circuit import CircuitBreakers, CircuitOpen


def test_closed_by_default() -> None:
    cb = CircuitBreakers(failure_threshold=2, cooldown_seconds=0.5)
    cb.ensure_closed("openai", "gpt-4o-mini")  # no exception


def test_opens_after_threshold() -> None:
    cb = CircuitBreakers(failure_threshold=2, cooldown_seconds=0.5)
    cb.record_failure("openai", "gpt-4o-mini")
    cb.record_failure("openai", "gpt-4o-mini")
    with pytest.raises(CircuitOpen):
        cb.ensure_closed("openai", "gpt-4o-mini")


def test_success_resets_counter() -> None:
    cb = CircuitBreakers(failure_threshold=2, cooldown_seconds=0.5)
    cb.record_failure("a", "m")
    cb.record_success("a", "m")
    cb.record_failure("a", "m")  # below threshold again
    cb.ensure_closed("a", "m")


def test_half_open_after_cooldown(monkeypatch) -> None:
    cb = CircuitBreakers(failure_threshold=1, cooldown_seconds=0.05)
    cb.record_failure("p", "m")
    with pytest.raises(CircuitOpen):
        cb.ensure_closed("p", "m")
    time.sleep(0.07)
    cb.ensure_closed("p", "m")  # half-open: no exception


def test_isolated_per_pair() -> None:
    cb = CircuitBreakers(failure_threshold=1, cooldown_seconds=10)
    cb.record_failure("openai", "gpt-4o-mini")
    with pytest.raises(CircuitOpen):
        cb.ensure_closed("openai", "gpt-4o-mini")
    cb.ensure_closed("openai", "gpt-4o")  # different model, separate breaker
    cb.ensure_closed("anthropic", "claude-haiku-4-5")
