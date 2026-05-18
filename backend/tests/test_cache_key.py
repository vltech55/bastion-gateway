from __future__ import annotations

from gateway.cache.redis_cache import cache_key, is_cacheable
from gateway.providers.base import ChatMessage


def _msgs():
    return [
        ChatMessage(role="system", content="You are helpful."),
        ChatMessage(role="user", content="Hi"),
    ]


def test_key_is_deterministic() -> None:
    k1 = cache_key("openai", "gpt-4o-mini", _msgs(), 100, 0.0)
    k2 = cache_key("openai", "gpt-4o-mini", _msgs(), 100, 0.0)
    assert k1 == k2


def test_key_differs_by_provider() -> None:
    a = cache_key("openai", "gpt-4o-mini", _msgs(), 100, 0.0)
    b = cache_key("anthropic", "gpt-4o-mini", _msgs(), 100, 0.0)
    assert a != b


def test_key_differs_by_messages() -> None:
    a = cache_key("openai", "gpt-4o-mini", _msgs(), 100, 0.0)
    other = _msgs() + [ChatMessage(role="user", content="Different")]
    b = cache_key("openai", "gpt-4o-mini", other, 100, 0.0)
    assert a != b


def test_temperature_rounded() -> None:
    a = cache_key("openai", "gpt-4o-mini", _msgs(), 100, 0.0)
    b = cache_key("openai", "gpt-4o-mini", _msgs(), 100, 0.00001)
    assert a == b  # rounded to 4dp


def test_is_cacheable_threshold() -> None:
    assert is_cacheable(0.0)
    assert not is_cacheable(0.7)
