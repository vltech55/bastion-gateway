from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    anthropic_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    aws_region: str = Field(default="us-east-1")
    bedrock_claude_model_id: str = Field(default="anthropic.claude-3-5-sonnet-20241022-v2:0")

    database_url: str = Field(default="postgresql+asyncpg://gateway:gateway@postgres:5432/gateway")
    redis_url: str = Field(default="redis://redis:6379/0")

    gateway_api_keys: str = Field(default="")
    cache_ttl_seconds: int = Field(default=86400, ge=10)
    cache_temp_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    rate_limit_tokens: int = Field(default=120, ge=1)
    rate_limit_refill_per_sec: float = Field(default=2.0, gt=0)
    circuit_breaker_failures: int = Field(default=3, ge=1)
    circuit_breaker_cooldown_seconds: float = Field(default=30.0, gt=0)

    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8080)
    log_level: str = Field(default="INFO")

    @property
    def api_key_set(self) -> set[str]:
        return {k.strip() for k in self.gateway_api_keys.split(",") if k.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
