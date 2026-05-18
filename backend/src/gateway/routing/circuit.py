from __future__ import annotations

import time
from dataclasses import dataclass

from gateway.core.config import settings
from gateway.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class _State:
    failures: int = 0
    opened_at: float | None = None


class CircuitOpen(RuntimeError):
    pass


class CircuitBreakers:
    """Per-(provider, model) breakers. Opens after N consecutive failures;
    auto-half-opens after `cooldown_seconds`. Single-process — fine for one
    gateway pod. For multi-replica, share via Redis."""

    def __init__(
        self,
        failure_threshold: int | None = None,
        cooldown_seconds: float | None = None,
    ) -> None:
        self.threshold = failure_threshold or settings.circuit_breaker_failures
        self.cooldown = cooldown_seconds or settings.circuit_breaker_cooldown_seconds
        self._states: dict[tuple[str, str], _State] = {}

    def _key(self, provider: str, model: str) -> tuple[str, str]:
        return (provider, model)

    def ensure_closed(self, provider: str, model: str) -> None:
        k = self._key(provider, model)
        s = self._states.get(k)
        if s is None or s.opened_at is None:
            return
        if time.monotonic() - s.opened_at >= self.cooldown:
            log.info("circuit_half_open", provider=provider, model=model)
            s.opened_at = None
            s.failures = 0
            return
        raise CircuitOpen(f"{provider}:{model} circuit is open")

    def record_success(self, provider: str, model: str) -> None:
        self._states.pop(self._key(provider, model), None)

    def record_failure(self, provider: str, model: str) -> None:
        k = self._key(provider, model)
        s = self._states.setdefault(k, _State())
        s.failures += 1
        if s.failures >= self.threshold:
            s.opened_at = time.monotonic()
            log.warning(
                "circuit_opened",
                provider=provider,
                model=model,
                failures=s.failures,
                cooldown=self.cooldown,
            )

    def health(self) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for (p, m), s in self._states.items():
            out.setdefault(p, {})[m] = "open" if s.opened_at is not None else "degraded"
        return out


breakers = CircuitBreakers()
