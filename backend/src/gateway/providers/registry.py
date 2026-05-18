from __future__ import annotations

from functools import lru_cache

from gateway.providers.anthropic_provider import AnthropicAdapter
from gateway.providers.base import ProviderAdapter
from gateway.providers.bedrock_provider import BedrockAdapter
from gateway.providers.openai_provider import OpenAIAdapter


@lru_cache(maxsize=1)
def adapters() -> dict[str, ProviderAdapter]:
    return {
        "openai": OpenAIAdapter(),
        "anthropic": AnthropicAdapter(),
        "bedrock": BedrockAdapter(),
    }


def get_adapter(name: str) -> ProviderAdapter:
    table = adapters()
    if name not in table:
        raise KeyError(f"unknown provider: {name}")
    return table[name]
