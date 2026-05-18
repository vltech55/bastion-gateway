from __future__ import annotations

from fastapi import APIRouter, Depends

from gateway.auth.api_key import require_api_key
from gateway.routing.policy import ROUTES

router = APIRouter(prefix="/v1", tags=["models"])


@router.get("/models")
async def list_models(_: str = Depends(require_api_key)) -> dict:
    return {
        "data": [
            {
                "id": alias,
                "candidates": [{"provider": c.provider, "model": c.model} for c in chain],
            }
            for alias, chain in ROUTES.items()
        ]
    }
