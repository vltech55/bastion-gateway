"""Drive synthetic traffic at the gateway to populate Grafana panels.

Sends a mix of unique + repeated prompts at temperature=0 so the cache exercise
is realistic — the dashboard's cache_hit_rate should climb past 50% after the
warm-up window. Run inside the container:
    docker compose exec gateway python -m scripts.load_test
"""
from __future__ import annotations

import asyncio
import os
import random

import httpx

from gateway.core.logging import configure_logging, get_logger

_BASE = "http://localhost:8080"
_KEY = os.environ.get("GATEWAY_API_KEYS", "demo-key-please-rotate").split(",")[0]

_REPEATED = [
    "What is reciprocal rank fusion?",
    "Explain HNSW indexes in one paragraph.",
    "What does a circuit breaker do in a service mesh?",
    "Summarize the difference between LangChain and LangGraph.",
]
_UNIQUE_PREFIXES = ["Tell me about", "Briefly describe", "In one line, what is", "Explain"]
_UNIQUE_TOPICS = ["pgvector", "rate limiting", "OpenAPI", "Redis Lua scripts", "FastAPI middleware"]


async def one_request(client: httpx.AsyncClient, prompt: str, model: str) -> None:
    try:
        r = await client.post(
            f"{_BASE}/v1/chat",
            headers={"X-API-Key": _KEY, "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.0,
            },
        )
        log = get_logger("load")
        if r.status_code != 200:
            log.warning("non_200", code=r.status_code, body=r.text[:160])
            return
        data = r.json()
        log.info(
            "ok",
            model=data["model_requested"],
            cache_hit=data["cache_hit"],
            latency_ms=data["latency_ms"],
            cost_usd=data["cost_usd"],
        )
    except httpx.HTTPError as exc:
        get_logger("load").warning("request_failed", error=str(exc))


async def main() -> None:
    configure_logging()
    log = get_logger("load")
    log.info("starting", base=_BASE, key_prefix=_KEY[:8])
    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(40):
            # 70/30 mix: repeated prompts (cacheable) vs unique (always uncached).
            if random.random() < 0.7:
                prompt = random.choice(_REPEATED)
            else:
                prompt = f"{random.choice(_UNIQUE_PREFIXES)} {random.choice(_UNIQUE_TOPICS)} ({i})"
            model = random.choice(["default-fast", "default-smart"])
            await one_request(client, prompt, model)
            await asyncio.sleep(0.5)
    log.info("done")


if __name__ == "__main__":
    asyncio.run(main())
