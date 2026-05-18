from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
    role: str = Field(pattern=r"^(system|user|assistant)$")
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    model: str = Field(min_length=1, description="Gateway alias (e.g. default-fast) or 'provider:model'.")
    messages: list[ChatMessageIn] = Field(min_length=1)
    max_tokens: int = Field(default=512, ge=1, le=8192)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    stream: bool = Field(default=False)


class ChatResponseOut(BaseModel):
    id: UUID
    model_requested: str
    provider: str
    model_chosen: str
    content: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: float
    cache_hit: bool
    fallback_chain: list[dict[str, str]]


class UsageRowOut(BaseModel):
    day: str
    requests: int
    cache_hit_rate: float
    cost_usd: float
    prompt_tokens: int
    completion_tokens: int


class UsageOut(BaseModel):
    n_days: int
    total_cost_usd: float
    total_requests: int
    cache_hit_rate: float
    daily: list[UsageRowOut]
