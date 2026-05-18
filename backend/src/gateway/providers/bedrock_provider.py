from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from gateway.core.config import settings
from gateway.providers.base import (
    ChatMessage,
    ChatRequestInput,
    ChatResponse,
    ProviderUnavailableError,
    StreamChunk,
)


@lru_cache(maxsize=1)
def _client() -> Any:
    if not (settings.aws_access_key_id and settings.aws_secret_access_key):
        raise ProviderUnavailableError("AWS credentials not set; Bedrock adapter inactive")
    import boto3  # type: ignore[import-untyped]

    return boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def _to_anthropic_body(req: ChatRequestInput) -> dict:
    system_parts = [m.content for m in req.messages if m.role == "system"]
    messages = [{"role": m.role, "content": m.content} for m in req.messages if m.role != "system"]
    return {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "system": "\n\n".join(system_parts) or "You are a helpful assistant.",
        "messages": messages,
    }


class BedrockAdapter:
    """AWS Bedrock adapter, currently scoped to Claude models on Bedrock.

    If AWS credentials aren't configured the adapter is dormant and raises
    `ProviderUnavailableError` immediately; the router falls through to the
    next provider in the chain. Activate by setting AWS_ACCESS_KEY_ID /
    AWS_SECRET_ACCESS_KEY / AWS_REGION plus BEDROCK_CLAUDE_MODEL_ID."""

    name = "bedrock"
    supports_streaming = True

    async def chat(self, req: ChatRequestInput) -> ChatResponse:
        client = _client()
        body = _to_anthropic_body(req)
        try:
            resp = await asyncio.to_thread(
                client.invoke_model,
                modelId=req.model,
                body=json.dumps(body),
                accept="application/json",
                contentType="application/json",
            )
            data = json.loads(resp["body"].read())
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"bedrock invoke failed: {exc}") from exc

        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage", {})
        return ChatResponse(
            content=text,
            prompt_tokens=int(usage.get("input_tokens", 0)),
            completion_tokens=int(usage.get("output_tokens", 0)),
            provider=self.name,
            model=req.model,
        )

    async def chat_stream(self, req: ChatRequestInput) -> AsyncIterator[StreamChunk]:
        client = _client()
        body = _to_anthropic_body(req)
        try:
            resp = await asyncio.to_thread(
                client.invoke_model_with_response_stream,
                modelId=req.model,
                body=json.dumps(body),
            )
            stream = resp["body"]
        except Exception as exc:
            raise ProviderUnavailableError(f"bedrock stream failed: {exc}") from exc

        # boto3 returns a blocking iterator; pump it through a worker thread to keep
        # the event loop responsive. Usage on Bedrock's Anthropic stream is split:
        # message_start carries input_tokens, message_delta carries cumulative
        # output_tokens. We surface both on the sentinel yield at end.
        loop = asyncio.get_running_loop()
        it = iter(stream)
        prompt_tokens, completion_tokens = 0, 0
        while True:
            event = await loop.run_in_executor(None, lambda: next(it, None))
            if event is None:
                break
            chunk = event.get("chunk", {}).get("bytes")
            if not chunk:
                continue
            obj = json.loads(chunk)
            ev_type = obj.get("type")
            if ev_type == "content_block_delta":
                delta = obj.get("delta", {})
                if delta.get("type") == "text_delta":
                    yield delta.get("text", ""), None, None
            elif ev_type == "message_start":
                usage = obj.get("message", {}).get("usage", {})
                prompt_tokens = int(usage.get("input_tokens", prompt_tokens))
            elif ev_type == "message_delta":
                usage = obj.get("usage", {})
                completion_tokens = int(usage.get("output_tokens", completion_tokens))
        yield "", prompt_tokens, completion_tokens
