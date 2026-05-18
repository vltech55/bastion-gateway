from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from gateway.auth.api_key import require_api_key
from gateway.cache import redis_cache
from gateway.core.logging import get_logger
from gateway.core.pricing import compute_cost
from gateway.db import get_session
from gateway.models import Request as RequestRow
from gateway.observability.metrics import (
    CACHE_HITS,
    CACHE_MISSES,
    CIRCUIT_OPEN,
    GATEWAY_OVERHEAD,
    PROVIDER_FAILURES,
    REQUEST_COST,
    REQUEST_LATENCY,
    REQUEST_TOKENS,
    REQUESTS_TOTAL,
)
from gateway.providers.base import ChatMessage, ChatRequestInput, ProviderUnavailableError
from gateway.providers.registry import get_adapter
from gateway.ratelimit.redis_bucket import take as rl_take
from gateway.routing.circuit import CircuitOpen, breakers
from gateway.routing.policy import candidates_for
from gateway.schemas import ChatRequest, ChatResponseOut

router = APIRouter(prefix="/v1", tags=["chat"])
log = get_logger(__name__)


async def _enforce_rate_limit(api_key_hash: str, max_tokens: int) -> None:
    cost = 1.0 + max_tokens / 1000.0  # bigger requests cost more bucket tokens
    allowed, retry = await rl_take(api_key_hash, cost=cost)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": f"{retry:.1f}"},
        )


@router.post("/chat", response_model=ChatResponseOut)
async def chat(
    body: ChatRequest,
    response: Response,
    api_key_hash: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> ChatResponseOut:
    if body.stream:
        raise HTTPException(
            status_code=400,
            detail="this endpoint returns JSON; use POST /v1/chat/stream for SSE",
        )
    await _enforce_rate_limit(api_key_hash, body.max_tokens)

    try:
        candidates = candidates_for(body.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    messages = [ChatMessage(role=m.role, content=m.content) for m in body.messages]
    started = time.perf_counter()

    # ---- cache lookup ----
    cache_hit = False
    if redis_cache.is_cacheable(body.temperature):
        primary = candidates[0]
        key = redis_cache.cache_key(primary.provider, primary.model, messages, body.max_tokens, body.temperature)
        cached = await redis_cache.get(key)
        if cached is not None:
            cache_hit = True
            CACHE_HITS.inc()
            response.headers["X-Cache"] = "HIT"
            REQUESTS_TOTAL.labels(primary.provider, primary.model, "ok", "hit").inc()
            REQUEST_LATENCY.labels(primary.provider, primary.model, "hit").observe(
                (time.perf_counter() - started)
            )
            row = RequestRow(
                api_key_hash=api_key_hash,
                requested_model=body.model,
                chosen_provider=primary.provider,
                chosen_model=primary.model,
                prompt_tokens=cached.prompt_tokens,
                completion_tokens=cached.completion_tokens,
                cost_usd=0.0,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                cache_hit=True,
                status="ok",
                fallback_chain={"chain": [{"provider": primary.provider, "model": primary.model, "result": "cache"}]},
            )
            session.add(row)
            await session.commit()
            return ChatResponseOut(
                id=row.id,
                model_requested=body.model,
                provider=primary.provider,
                model_chosen=primary.model,
                content=cached.content,
                prompt_tokens=cached.prompt_tokens,
                completion_tokens=cached.completion_tokens,
                cost_usd=0.0,
                latency_ms=row.latency_ms,
                cache_hit=True,
                fallback_chain=[{"provider": primary.provider, "model": primary.model, "result": "cache"}],
            )

    CACHE_MISSES.inc()
    response.headers["X-Cache"] = "MISS"

    # ---- fallback chain ----
    last_error: Exception | None = None
    chain_log: list[dict[str, str]] = []
    for c in candidates:
        try:
            breakers.ensure_closed(c.provider, c.model)
        except CircuitOpen as exc:
            CIRCUIT_OPEN.labels(c.provider, c.model).set(1)
            chain_log.append({"provider": c.provider, "model": c.model, "result": "circuit_open"})
            last_error = exc
            continue

        adapter = get_adapter(c.provider)
        try:
            t_pre = time.perf_counter()
            resp = await adapter.chat(
                ChatRequestInput(
                    model=c.model,
                    messages=messages,
                    max_tokens=body.max_tokens,
                    temperature=body.temperature,
                )
            )
            elapsed = time.perf_counter() - started
            upstream = time.perf_counter() - t_pre
        except ProviderUnavailableError as exc:
            PROVIDER_FAILURES.labels(c.provider, c.model).inc()
            breakers.record_failure(c.provider, c.model)
            chain_log.append({"provider": c.provider, "model": c.model, "result": f"failed: {exc}"})
            last_error = exc
            continue

        breakers.record_success(c.provider, c.model)
        CIRCUIT_OPEN.labels(c.provider, c.model).set(0)

        cost = compute_cost(c.provider, c.model, resp.prompt_tokens, resp.completion_tokens)
        REQUEST_LATENCY.labels(c.provider, c.model, "miss").observe(elapsed)
        GATEWAY_OVERHEAD.labels("miss").observe(max(0.0, elapsed - upstream))
        REQUESTS_TOTAL.labels(c.provider, c.model, "ok", "miss").inc()
        REQUEST_TOKENS.labels(c.provider, c.model, "prompt").inc(resp.prompt_tokens)
        REQUEST_TOKENS.labels(c.provider, c.model, "completion").inc(resp.completion_tokens)
        REQUEST_COST.labels(c.provider, c.model).inc(cost.total_usd)

        chain_log.append({"provider": c.provider, "model": c.model, "result": "ok"})

        if redis_cache.is_cacheable(body.temperature):
            key = redis_cache.cache_key(c.provider, c.model, messages, body.max_tokens, body.temperature)
            await redis_cache.set_(key, redis_cache.CachedResponse.from_response(resp))

        row = RequestRow(
            api_key_hash=api_key_hash,
            requested_model=body.model,
            chosen_provider=c.provider,
            chosen_model=c.model,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            cost_usd=cost.total_usd,
            latency_ms=round(elapsed * 1000, 2),
            cache_hit=cache_hit,
            status="ok",
            fallback_chain={"chain": chain_log},
        )
        session.add(row)
        await session.commit()

        return ChatResponseOut(
            id=row.id,
            model_requested=body.model,
            provider=c.provider,
            model_chosen=c.model,
            content=resp.content,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            cost_usd=cost.total_usd,
            latency_ms=row.latency_ms,
            cache_hit=False,
            fallback_chain=chain_log,
        )

    # Every candidate failed.
    row = RequestRow(
        api_key_hash=api_key_hash,
        requested_model=body.model,
        chosen_provider="none",
        chosen_model="none",
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
        cache_hit=False,
        status="failed",
        error=str(last_error) if last_error else "no candidates",
        fallback_chain={"chain": chain_log},
    )
    session.add(row)
    await session.commit()
    REQUESTS_TOTAL.labels("none", "none", "failed", "miss").inc()
    raise HTTPException(status_code=502, detail=f"all providers failed: {last_error}")


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    api_key_hash: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> EventSourceResponse:
    await _enforce_rate_limit(api_key_hash, body.max_tokens)
    try:
        candidates = candidates_for(body.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    messages = [ChatMessage(role=m.role, content=m.content) for m in body.messages]

    async def gen() -> AsyncIterator[dict[str, str]]:
        started = time.perf_counter()
        for c in candidates:
            try:
                breakers.ensure_closed(c.provider, c.model)
            except CircuitOpen:
                yield {"event": "fallback", "data": json.dumps({"provider": c.provider, "model": c.model, "reason": "circuit_open"})}
                continue
            adapter = get_adapter(c.provider)
            try:
                yield {"event": "open", "data": json.dumps({"provider": c.provider, "model": c.model})}
                buf: list[str] = []
                prompt_tokens, completion_tokens = 0, 0
                async for delta, p_tok, c_tok in adapter.chat_stream(
                    ChatRequestInput(
                        model=c.model, messages=messages,
                        max_tokens=body.max_tokens, temperature=body.temperature,
                    )
                ):
                    if delta:
                        buf.append(delta)
                        yield {"event": "token", "data": json.dumps({"text": delta})}
                    # Sentinel: text-empty chunk carrying the final usage counts.
                    if p_tok is not None and c_tok is not None:
                        prompt_tokens, completion_tokens = p_tok, c_tok
                breakers.record_success(c.provider, c.model)

                elapsed = time.perf_counter() - started
                cost = compute_cost(c.provider, c.model, prompt_tokens, completion_tokens)
                REQUEST_LATENCY.labels(c.provider, c.model, "miss").observe(elapsed)
                REQUESTS_TOTAL.labels(c.provider, c.model, "ok", "miss").inc()
                REQUEST_TOKENS.labels(c.provider, c.model, "prompt").inc(prompt_tokens)
                REQUEST_TOKENS.labels(c.provider, c.model, "completion").inc(completion_tokens)
                REQUEST_COST.labels(c.provider, c.model).inc(cost.total_usd)

                row = RequestRow(
                    api_key_hash=api_key_hash,
                    requested_model=body.model,
                    chosen_provider=c.provider,
                    chosen_model=c.model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost.total_usd,
                    latency_ms=round(elapsed * 1000, 2),
                    cache_hit=False,
                    status="ok",
                    fallback_chain={"streamed": True, "provider": c.provider, "model": c.model},
                )
                session.add(row)
                await session.commit()
                yield {
                    "event": "done",
                    "data": json.dumps({
                        "latency_ms": round(elapsed * 1000, 2),
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "cost_usd": cost.total_usd,
                    }),
                }
                return
            except ProviderUnavailableError as exc:
                PROVIDER_FAILURES.labels(c.provider, c.model).inc()
                breakers.record_failure(c.provider, c.model)
                yield {"event": "fallback", "data": json.dumps({"provider": c.provider, "model": c.model, "reason": str(exc)})}
                continue
        yield {"event": "error", "data": json.dumps({"detail": "all providers failed"})}

    return EventSourceResponse(gen())
