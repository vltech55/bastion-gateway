from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache

import redis.asyncio as aioredis

from gateway.core.config import settings
from gateway.providers.base import ChatMessage, ChatResponse


def cache_key(provider: str, model: str, messages: list[ChatMessage], max_tokens: int, temperature: float) -> str:
    """Deterministic key per (provider, model, prompt). Floats are rounded to 4
    decimals so 0.0 and 0.00 hash the same. Messages are JSON-serialized in their
    canonical role/content shape — no whitespace dependence."""
    payload = {
        "provider": provider,
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "max_tokens": max_tokens,
        "temperature": round(temperature, 4),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return "gw:cache:" + hashlib.sha256(raw).hexdigest()


def is_cacheable(temperature: float) -> bool:
    """Only cache deterministic-ish requests. Tunable via CACHE_TEMP_THRESHOLD."""
    return temperature <= settings.cache_temp_threshold


@dataclass(frozen=True)
class CachedResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    provider: str
    model: str

    @classmethod
    def from_response(cls, r: ChatResponse) -> CachedResponse:
        return cls(r.content, r.prompt_tokens, r.completion_tokens, r.provider, r.model)

    def to_response(self) -> ChatResponse:
        return ChatResponse(
            content=self.content,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            provider=self.provider,
            model=self.model,
        )


@lru_cache(maxsize=1)
def _redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def get(key: str) -> CachedResponse | None:
    raw = await _redis().get(key)
    if raw is None:
        return None
    try:
        d = json.loads(raw)
        return CachedResponse(**d)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


async def set_(key: str, value: CachedResponse, ttl: int | None = None) -> None:
    await _redis().set(
        key,
        json.dumps({
            "content": value.content,
            "prompt_tokens": value.prompt_tokens,
            "completion_tokens": value.completion_tokens,
            "provider": value.provider,
            "model": value.model,
        }),
        ex=ttl or settings.cache_ttl_seconds,
    )
