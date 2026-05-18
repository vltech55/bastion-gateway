from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gateway import __version__
from gateway.api import chat, health, models, usage
from gateway.core.config import settings
from gateway.core.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log.info(
        "startup",
        version=__version__,
        rate_limit_tokens=settings.rate_limit_tokens,
        cache_ttl=settings.cache_ttl_seconds,
        api_keys_configured=bool(settings.api_key_set),
    )
    if not settings.api_key_set:
        log.warning("auth_disabled_dev_mode", note="set GATEWAY_API_KEYS before production")
    yield
    log.info("shutdown")


app = FastAPI(
    title="LLM Gateway",
    version=__version__,
    description=(
        "Unified API over OpenAI / Anthropic / AWS Bedrock with caching, "
        "automatic fallback, per-key rate limiting, cost tracking, and "
        "Prometheus metrics for Grafana dashboards."
    ),
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    start = time.perf_counter()
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id, path=request.url.path, method=request.method
    )
    try:
        response = await call_next(request)
    except Exception as exc:
        log.exception("unhandled", error=str(exc))
        return JSONResponse(status_code=500, content={"detail": "internal", "request_id": request_id})
    elapsed = (time.perf_counter() - start) * 1000
    response.headers["x-request-id"] = request_id
    response.headers["x-response-time-ms"] = f"{elapsed:.1f}"
    log.info("request", status=response.status_code, elapsed_ms=round(elapsed, 1))
    return response


app.include_router(health.router)
app.include_router(chat.router)
app.include_router(models.router)
app.include_router(usage.router)
