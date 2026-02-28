"""
Reference data endpoints — read-only, authenticated.

Results are cached in memory with a 5-minute TTL (except /provinces which
queries live data and is not cached).
"""
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.rbac import require_role
from app.core.security import get_current_user
from app.models.reference import RefComplaintType, RefServiceType, RefClosureReason
from app.models.sla import SlaConfig
from app.schemas.reference import (
    ClosureReasonResponse,
    ComplaintTypeResponse,
    ProvinceItem,
    ServiceTypeResponse,
    SlaConfigResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reference", tags=["reference"])

# ---------------------------------------------------------------------------
# Simple in-memory TTL cache (avoids adding a Redis dependency for ref data)
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 300  # 5 minutes


def _cache_get(key: str) -> Any | None:
    if key in _cache:
        ts, value = _cache[key]
        if time.monotonic() - ts < _CACHE_TTL:
            return value
        del _cache[key]
    return None


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.monotonic(), value)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/service-types", response_model=list[ServiceTypeResponse])
async def get_service_types(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[ServiceTypeResponse]:
    cached = _cache_get("service_types")
    if cached is not None:
        return cached

    result = await db.execute(select(RefServiceType).order_by(RefServiceType.code))
    rows = result.scalars().all()
    data = [ServiceTypeResponse.model_validate(r) for r in rows]
    _cache_set("service_types", data)
    return data


@router.get("/complaint-types", response_model=list[ComplaintTypeResponse])
async def get_complaint_types(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[ComplaintTypeResponse]:
    cached = _cache_get("complaint_types")
    if cached is not None:
        return cached

    result = await db.execute(select(RefComplaintType).order_by(RefComplaintType.code))
    rows = result.scalars().all()
    data = [ComplaintTypeResponse.model_validate(r) for r in rows]
    _cache_set("complaint_types", data)
    return data


@router.get("/closure-reasons", response_model=list[ClosureReasonResponse])
async def get_closure_reasons(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[ClosureReasonResponse]:
    cached = _cache_get("closure_reasons")
    if cached is not None:
        return cached

    result = await db.execute(select(RefClosureReason).order_by(RefClosureReason.code))
    rows = result.scalars().all()
    data = [ClosureReasonResponse.model_validate(r) for r in rows]
    _cache_set("closure_reasons", data)
    return data


@router.get("/provinces", response_model=list[ProvinceItem])
async def get_provinces(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[ProvinceItem]:
    """Distinct provinces from cases (live query, no cache)."""
    result = await db.execute(
        text("SELECT DISTINCT province FROM cases WHERE province IS NOT NULL ORDER BY province")
    )
    rows = result.fetchall()
    return [ProvinceItem(province=r[0]) for r in rows]


@router.get("/sla-config", response_model=list[SlaConfigResponse])
async def get_sla_config(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role("ADMIN")),
) -> list[SlaConfigResponse]:
    """SLA configuration — Admin only."""
    cached = _cache_get("sla_config")
    if cached is not None:
        return cached

    result = await db.execute(select(SlaConfig).order_by(SlaConfig.priority))
    rows = result.scalars().all()
    data = [SlaConfigResponse.model_validate(r) for r in rows]
    _cache_set("sla_config", data)
    return data
