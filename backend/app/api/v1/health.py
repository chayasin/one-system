"""
GET /health — ALB health check endpoint.

No authentication required. Returns DB connectivity status.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.db import check_db_connection

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    db: str


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    db_ok = await check_db_connection()
    return HealthResponse(
        status="ok",
        db="ok" if db_ok else "error",
    )
