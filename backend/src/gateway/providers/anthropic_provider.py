from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from anthropic import AsyncAnthropic

from gateway.core.config import settings
from gateway.providers.base import (
    ChatMessage,
    ChatRequestInput,
    ChatResponse,
    ProviderUnavailableError,
)


@lru_cache(maxsize=1)
def _client() -> AsyncAnthropic:
    if not settings.anthropic_api_key:
        raise ProviderUnavailableError("ANTHROPIC_API_KEY not set")
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _split_system(messages: list[ChatMessage]) -> tuple[str, list[dict]]:
    system_parts = [m.content for m in messages if m.role == "system"]
    rest = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    return "\n\n".join(system_parts), rest


class AnthropicAdapter:
    name = "anthropic"
    supports_streaming = True

    async def chat(self, req: ChatRequestInput) -> ChatResponse:
        client = _client()
        system, messages = _split_system(req.messages)
        try:
            resp = await client.messages.create(
                model=req.model,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                system=system or "You are a helpful assistant.",
                messages=messages,
            )
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"anthropic chat failed: {exc}") from exc
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return ChatResponse(
            content=text,
            prompt_tokens=resp.usage.input_tokens,
            completion_tokens=resp.usage.output_tokens,
            provider=self.name,
            model=req.model,
        )

    async def chat_stream(self, req: ChatRequestInput) -> AsyncIterator[str]:
        client = _client()
        system, messages = _split_system(req.messages)
        try:
            async with client.messages.stream(
                model=req.model,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                system=system or "You are a helpful assistant.",
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            raise ProviderUnavailableError(f"anthropic stream failed: {exc}") from exc
