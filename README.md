# LLM Gateway: Observable & Cost-Aware

A production-pattern LLM gateway sitting between applications and three
upstream providers — OpenAI, Anthropic, and AWS Bedrock — with a unified
API, automatic provider fallback, Redis response caching, per-request cost
tracking, atomic Redis-backed rate limiting, structured logs, Prometheus
metrics, a Grafana dashboard, and Kubernetes manifests.

> **Why this exists:** teams running LLMs in production typically have no
> visibility into cost-per-request, no fallback when a provider fails, no
> caching, and no way to A/B test models safely. They learn this only
> after their first surprise invoice or outage. This project demonstrates
> the gateway pattern that solves all of these.

---

## Architecture

```
   client                 ┌───────── Redis ─────────┐
     │                    │  token bucket (Lua)     │
     │ X-API-Key          │  response cache (sha256)│
     ▼                    └─────────────────────────┘
  ┌───────────────────────── FastAPI ─────────────────────────┐
  │  auth → rate limit → cache lookup → route → fallback     │
  │                                       │                  │
  │                                       ▼                  │
  │       OpenAI  ─────────────────┐                         │
  │       Anthropic ────  Circuit  ── ProviderAdapter        │
  │       Bedrock  ─────  breaker ─┘   (Protocol)            │
  │                                       │                  │
  │            ┌─── usage ────────────────┘                  │
  │            ▼                                              │
  │   Postgres (requests table)        Prometheus /metrics    │
  └───────────────────────────────────────────────────────────┘
                                              │
                                              ▼
                                          Grafana
```

Full mermaid diagram + lifecycle notes: [`docs/architecture.md`](./docs/architecture.md).

## Stack

- **API:** Python 3.11, FastAPI async, structured logging via structlog
- **Providers:** Anthropic SDK, OpenAI SDK, boto3 (Bedrock)
- **Cache + rate limit:** Redis 7 (response cache + atomic Lua token bucket)
- **DB:** Postgres 16; `requests` table records every request (provider, model, tokens, cost, latency, cache_hit, status, fallback chain JSONB)
- **Observability:** `prometheus_client` for `/metrics`; Prometheus + Grafana with auto-provisioned datasource & dashboard
- **Deployment:** docker-compose for dev; K8s manifests (deployment, service, configmap, secret example, HPA, ServiceMonitor) for prod
- **Reliability:** per-(provider, model) circuit breakers, tenacity-shaped retries inside each adapter

## Quick start

```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY + OPENAI_API_KEY at minimum.
# AWS_* + BEDROCK_CLAUDE_MODEL_ID are optional — Bedrock falls through to the
# next candidate in the chain if creds are missing.

make up                    # gateway + postgres + redis + prometheus + grafana
make migrate               # alembic upgrade head
make load                  # drive synthetic traffic to populate the dashboard

# Open:
#   http://localhost:8080/docs    OpenAPI
#   http://localhost:9090         Prometheus
#   http://localhost:3003         Grafana (admin/admin) → dashboard auto-provisioned
```

## Unified API

```bash
curl -X POST http://localhost:8080/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-key-please-rotate" \
  -d '{
    "model": "default-fast",
    "messages": [{"role": "user", "content": "What is RRF?"}],
    "max_tokens": 200,
    "temperature": 0.0
  }'
```

Response:

```json
{
  "id": "...",
  "model_requested": "default-fast",
  "provider": "openai",
  "model_chosen": "gpt-4o-mini",
  "content": "...",
  "prompt_tokens": 42,
  "completion_tokens": 87,
  "cost_usd": 0.0001,
  "latency_ms": 612.3,
  "cache_hit": false,
  "fallback_chain": [{"provider": "openai", "model": "gpt-4o-mini", "result": "ok"}]
}
```

Re-running the same body returns instantly with `cache_hit: true` and `cost_usd: 0`.

## Model aliases

| Alias                            | Fallback chain                                                                       |
| -------------------------------- | ------------------------------------------------------------------------------------ |
| `default-fast`                   | openai:gpt-4o-mini → anthropic:claude-haiku-4-5                                      |
| `default-smart`                  | anthropic:claude-sonnet-4-6 → bedrock:claude-3-5-sonnet → openai:gpt-4o              |
| `provider:model` (e.g. `openai:gpt-4o`) | Direct passthrough — no fallback                                              |

Add aliases in `routing/policy.py`. The chain order *is* the fallback order; a
candidate is skipped if its circuit is open or its adapter raises
`ProviderUnavailableError`.

## Endpoints

| Method | Path              | Purpose                                                |
| ------ | ----------------- | ------------------------------------------------------ |
| POST   | `/v1/chat`        | Unified JSON chat (with cache + fallback)              |
| POST   | `/v1/chat/stream` | Same routing, SSE token stream                         |
| GET    | `/v1/models`      | Aliases + fallback chains                              |
| GET    | `/v1/usage`       | Per-key daily roll-up: requests, cost, hit rate        |
| GET    | `/health`         | Liveness                                               |
| GET    | `/ready`          | Liveness + per-provider circuit state                  |
| GET    | `/metrics`        | Prometheus text format                                 |

## Observability

The bundled dashboard (`observability/grafana/dashboards/llm-gateway.json`) is
auto-provisioned at boot via the dashboards provisioning config. Panels:

- Requests/sec; Cache hit rate; Cost (1h); Open circuits
- Latency p50/p95/p99 by provider
- Gateway overhead (uncached path) — sub-100ms target
- Requests by provider+model
- Failure rate by provider
- Tokens prompt vs completion
- Cumulative cost by provider

All metric labels are bounded (provider, model, status, cache) so cardinality
stays sane in long-running prod deployments.

## Why a Lua token bucket

Token-bucket math needs atomicity under concurrency, and pipelining isn't
enough — multiple gateway pods sharing one Redis can otherwise let two
requests slip through past the cap simultaneously. The bundled Lua script
(`ratelimit/redis_bucket.py`) computes refill + decrement atomically and
returns a precise `Retry-After` value.

## Kubernetes

```
k8s/
├── namespace.yaml         llm-gateway namespace
├── configmap.yaml         non-secret tuning (TTL, rate limit, circuit)
├── secret.example.yaml    DO NOT commit real values
├── deployment.yaml        2-replica, prometheus.io annotations, probes, resource limits
├── service.yaml           ClusterIP on port 80 → 8080
├── hpa.yaml               2-12 replicas, CPU 70% target
└── servicemonitor.yaml    auto-scrape when running with kube-prometheus-stack
```

The `prometheus.io/*` pod annotations let unmodified Prometheus scrape without
a ServiceMonitor; the ServiceMonitor manifest is preferred when running
kube-prometheus-stack.

## Project layout

```
06-llm-gateway/
├── backend/src/gateway/
│   ├── core/             config, logging, pricing
│   ├── providers/        base Protocol + openai + anthropic + bedrock + registry
│   ├── routing/          policy + per-(provider,model) circuit breakers
│   ├── cache/            redis_cache (sha256 key + TTL + temp threshold)
│   ├── ratelimit/        atomic Lua token bucket
│   ├── auth/             X-API-Key with constant-time compare
│   ├── observability/    prometheus_client counters/histograms/gauges
│   ├── api/              chat (sync + SSE), models, usage, health (+ /metrics)
│   ├── db.py             async engine
│   ├── models.py         api_keys, requests (with fallback_chain JSONB)
│   └── main.py           FastAPI app with request_id middleware
├── backend/alembic/      initial migration
├── backend/scripts/      load_test driving synthetic traffic for the dashboard
├── backend/tests/        cache key determinism, routing aliases, circuit, pricing
├── observability/
│   ├── prometheus.yml
│   └── grafana/
│       ├── datasources.yml
│       ├── dashboards.yml
│       └── dashboards/llm-gateway.json
├── k8s/                  deployment manifests
├── docs/architecture.md  mermaid + design rationale
├── docker-compose.yml    gateway + postgres + redis + prometheus + grafana
└── Makefile
```

## Make targets

```
make up         all five services
make migrate    alembic upgrade head
make load       drive synthetic traffic to populate Grafana
make test       pytest (cache key, routing, circuit, pricing)
make lint       ruff + mypy strict
make logs       tail logs
make psql       open psql shell
make clean      drop volumes
```

## What this isn't (yet)

- A/B prompt routing — the routing policy is static; prompt-version-based traffic split is a small add.
- Distributed circuit breakers — current breakers are in-process. Share via Redis for tightly coordinated multi-pod failure handling.
- Auto-generated SDKs — FastAPI's OpenAPI is shipped; running `openapi-generator` against it is a one-liner you'd add to CI.
- Cost-aware admission control — the gateway *records* cost but doesn't enforce a per-tenant spend cap. The data is there; the policy is a follow-up.

## License

MIT.
