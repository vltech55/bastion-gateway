from __future__ import annotations

import time
from functools import lru_cache

import redis.asyncio as aioredis

from gateway.core.config import settings

# Token bucket implemented atomically in Lua so concurrent calls from
# multiple gateway pods can share one Redis-backed bucket per API key.
_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
    tokens = capacity
    ts = now
end

local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * refill)
local allowed = 0
if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, 3600)
local retry = 0
if allowed == 0 and refill > 0 then
    retry = (cost - tokens) / refill
end
return {allowed, retry}
"""


@lru_cache(maxsize=1)
def _redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


_script_sha: str | None = None


async def _ensure_script() -> str:
    global _script_sha
    if _script_sha is None:
        _script_sha = await _redis().script_load(_LUA)
    return _script_sha


async def take(api_key_hash: str, *, cost: float = 1.0) -> tuple[bool, float]:
    """Try to take `cost` tokens for the bucket associated with this API key.

    Returns (allowed, retry_after_seconds). Bucket parameters come from
    settings; the algorithm is monotonic in `cost` so larger requests can
    cost more (e.g. proportional to `max_tokens`)."""
    sha = await _ensure_script()
    now = time.time()
    res = await _redis().evalsha(
        sha,
        1,
        f"gw:rl:{api_key_hash}",
        settings.rate_limit_tokens,
        settings.rate_limit_refill_per_sec,
        now,
        cost,
    )
    allowed = int(res[0]) == 1
    retry = float(res[1])
    return allowed, retry
