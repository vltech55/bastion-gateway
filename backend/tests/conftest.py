from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("GATEWAY_API_KEYS", "test-key-1,test-key-2")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://gateway:gateway@localhost:5437/gateway_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/0")
