from __future__ import annotations

import hashlib
import hmac

from fastapi import Header, HTTPException, status

from gateway.core.config import settings


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """FastAPI dependency. Returns the *hash* of the key for downstream use as a
    bucket identity / persistence key. Never store the raw key."""
    keys = settings.api_key_set
    if not keys:
        # Dev mode: no keys configured → accept anything (logged at startup).
        return "dev-no-auth"
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing X-API-Key")
    for k in keys:
        if hmac.compare_digest(x_api_key, k):
            return hash_key(x_api_key)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
