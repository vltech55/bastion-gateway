from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# All labels are bounded (provider/model/status/cache_hit) so cardinality stays sane.
REQUESTS_TOTAL = Counter(
    "gateway_requests_total",
    "Total requests handled by the gateway.",
    ["provider", "model", "status", "cache"],
)

REQUEST_LATENCY = Histogram(
    "gateway_request_latency_seconds",
    "End-to-end latency including upstream provider time.",
    ["provider", "model", "cache"],
    buckets=(0.02, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

GATEWAY_OVERHEAD = Histogram(
    "gateway_overhead_seconds",
    "Time spent inside the gateway excluding the upstream call.",
    ["cache"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
)

REQUEST_COST = Counter(
    "gateway_request_cost_usd_total",
    "Cumulative USD cost from upstream providers, summed.",
    ["provider", "model"],
)

REQUEST_TOKENS = Counter(
    "gateway_tokens_total",
    "Cumulative tokens.",
    ["provider", "model", "kind"],  # kind: prompt | completion
)

PROVIDER_FAILURES = Counter(
    "gateway_provider_failures_total",
    "Upstream provider failures (counted per candidate tried).",
    ["provider", "model"],
)

CACHE_HITS = Counter("gateway_cache_hits_total", "Cache hits.")
CACHE_MISSES = Counter("gateway_cache_misses_total", "Cache misses.")

CIRCUIT_OPEN = Gauge(
    "gateway_circuit_open",
    "1 if the circuit breaker is currently open for this provider+model.",
    ["provider", "model"],
)
