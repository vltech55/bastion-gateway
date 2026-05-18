from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    provider: str
    model: str


# Public model aliases route to ordered fallback chains.
# Bedrock entries are tried first when configured; the adapter raises
# ProviderUnavailableError if AWS keys are missing, so the router falls
# through to the next candidate transparently.
ROUTES: dict[str, list[Candidate]] = {
    "default-fast": [
        Candidate("openai", "gpt-4o-mini"),
        Candidate("anthropic", "claude-haiku-4-5"),
    ],
    "default-smart": [
        Candidate("anthropic", "claude-sonnet-4-6"),
        Candidate("bedrock", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
        Candidate("openai", "gpt-4o"),
    ],
    # Direct provider:model passthroughs let clients opt out of routing.
    "openai:gpt-4o-mini": [Candidate("openai", "gpt-4o-mini")],
    "openai:gpt-4o": [Candidate("openai", "gpt-4o")],
    "anthropic:claude-sonnet-4-6": [Candidate("anthropic", "claude-sonnet-4-6")],
    "anthropic:claude-haiku-4-5": [Candidate("anthropic", "claude-haiku-4-5")],
}


def candidates_for(requested: str) -> list[Candidate]:
    if requested in ROUTES:
        return ROUTES[requested]
    if ":" in requested:
        provider, model = requested.split(":", 1)
        return [Candidate(provider, model)]
    raise ValueError(
        f"unknown model alias '{requested}'. "
        f"Known aliases: {sorted(ROUTES.keys())} or use 'provider:model' form."
    )


def known_models() -> list[str]:
    return sorted(ROUTES.keys())
