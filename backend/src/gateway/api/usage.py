from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.auth.api_key import require_api_key
from gateway.db import get_session
from gateway.models import Request
from gateway.schemas import UsageOut, UsageRowOut

router = APIRouter(prefix="/v1", tags=["usage"])


@router.get("/usage", response_model=UsageOut)
async def usage(
    days: int = 30,
    api_key_hash: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> UsageOut:
    since = date.today() - timedelta(days=days - 1)
    rows = (
        await session.execute(
            select(
                func.date_trunc("day", Request.created_at).label("day"),
                func.count(Request.id).label("requests"),
                func.coalesce(func.sum(Request.cost_usd), 0).label("cost"),
                func.coalesce(func.sum(Request.prompt_tokens), 0).label("prompt"),
                func.coalesce(func.sum(Request.completion_tokens), 0).label("completion"),
                func.coalesce(
                    func.avg(func.case((Request.cache_hit.is_(True), 1.0), else_=0.0)),
                    0,
                ).label("hit_rate"),
            )
            .where(Request.api_key_hash == api_key_hash, Request.created_at >= since)
            .group_by("day")
            .order_by("day")
        )
    ).all()

    daily = [
        UsageRowOut(
            day=r.day.date().isoformat(),
            requests=int(r.requests),
            cache_hit_rate=round(float(r.hit_rate), 4),
            cost_usd=round(float(r.cost), 6),
            prompt_tokens=int(r.prompt),
            completion_tokens=int(r.completion),
        )
        for r in rows
    ]
    total_req = sum(d.requests for d in daily)
    total_cost = round(sum(d.cost_usd for d in daily), 6)
    overall_hit = (
        sum(d.cache_hit_rate * d.requests for d in daily) / total_req if total_req else 0.0
    )
    return UsageOut(
        n_days=days,
        total_cost_usd=total_cost,
        total_requests=total_req,
        cache_hit_rate=round(overall_hit, 4),
        daily=daily,
    )
