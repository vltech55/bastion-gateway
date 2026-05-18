from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ChatRequestInput:
    model: str            # provider-specific model id, set by routing policy
    messages: list[ChatMessage]
    max_tokens: int = 1024
    temperature: float = 0.2


@dataclass(frozen=True)
class ChatResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    provider: str
    model: str


class ProviderUnavailableError(RuntimeError):
    """Raised when a provider's credentials are missing or its API rejects the call.

    The router catches this and falls through to the next candidate in the chain."""


class ProviderAdapter(Protocol):
    name: str
    supports_streaming: bool

    async def chat(self, req: ChatRequestInput) -> ChatResponse: ...
    async def chat_stream(self, req: ChatRequestInput) -> AsyncIterator[str]: ...
