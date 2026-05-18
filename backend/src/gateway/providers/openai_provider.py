from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from openai import AsyncOpenAI

from gateway.core.config import settings
from gateway.providers.base import (
    ChatMessage,
    ChatRequestInput,
    ChatResponse,
    ProviderUnavailableError,
    StreamChunk,
)


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise ProviderUnavailableError("OPENAI_API_KEY not set")
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _msgs(messages: list[ChatMessage]) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in messages]


class OpenAIAdapter:
    name = "openai"
    supports_streaming = True

    async def chat(self, req: ChatRequestInput) -> ChatResponse:
        try:
            client = _client()
            resp = await client.chat.completions.create(
                model=req.model,
                messages=_msgs(req.messages),
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            )
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"openai chat failed: {exc}") from exc
        choice = resp.choices[0]
        usage = resp.usage
        return ChatResponse(
            content=choice.message.content or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            provider=self.name,
            model=req.model,
        )

    async def chat_stream(self, req: ChatRequestInput) -> AsyncIterator[StreamChunk]:
        client = _client()
        try:
            stream = await client.chat.completions.create(
                model=req.model,
                messages=_msgs(req.messages),
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                stream=True,
                # Without this flag OpenAI omits `usage` from streaming chunks. With it,
                # the final chunk carries final prompt/completion token counts.
                stream_options={"include_usage": True},
            )
        except Exception as exc:
            raise ProviderUnavailableError(f"openai stream open failed: {exc}") from exc

        prompt_tokens, completion_tokens = 0, 0
        async for chunk in stream:
            for c in chunk.choices:
                if c.delta and c.delta.content:
                    yield c.delta.content, None, None
            if chunk.usage is not None:
                prompt_tokens = chunk.usage.prompt_tokens
                completion_tokens = chunk.usage.completion_tokens
        yield "", prompt_tokens, completion_tokens
