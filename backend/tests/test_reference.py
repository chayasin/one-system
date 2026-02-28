"""
Tests for reference data endpoints.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reference import RefServiceType, RefComplaintType
from app.models.sla import SlaConfig


@pytest.mark.asyncio
async def test_get_service_types_empty(client):
    resp = await client.get("/api/v1/reference/service-types")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_service_types_with_data(client, db_session: AsyncSession):
    db_session.add(RefServiceType(code="ST01", label="ร้องเรียน", channel=None))
    db_session.add(RefServiceType(code="ST02", label="แจ้งข้อมูล", channel="LINE"))
    await db_session.commit()

    # Clear in-memory cache so the fresh DB rows are returned
    import app.api.v1.reference as ref_module
    ref_module._cache.clear()

    resp = await client.get("/api/v1/reference/service-types")
    assert resp.status_code == 200
    codes = [item["code"] for item in resp.json()]
    assert "ST01" in codes
    assert "ST02" in codes


@pytest.mark.asyncio
async def test_get_complaint_types(client, db_session: AsyncSession):
    db_session.add(RefComplaintType(code="CT01", label="ถนนเสียหาย"))
    await db_session.commit()

    import app.api.v1.reference as ref_module
    ref_module._cache.clear()

    resp = await client.get("/api/v1/reference/complaint-types")
    assert resp.status_code == 200
    assert any(item["code"] == "CT01" for item in resp.json())


@pytest.mark.asyncio
async def test_get_provinces_empty(client):
    resp = await client.get("/api/v1/reference/provinces")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_sla_config_admin_only(client, officer_user):
    """OFFICER must receive 403 on the sla-config endpoint."""
    resp = await client.get(
        "/api/v1/reference/sla-config",
        headers={"X-Dev-User-ID": officer_user.cognito_user_id},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_sla_config_admin(client, db_session: AsyncSession):
    db_session.add(
        SlaConfig(
            priority="CRITICAL",
            temp_fix_hours=12,
            permanent_fix_days=7,
        )
    )
    await db_session.commit()

    import app.api.v1.reference as ref_module
    ref_module._cache.clear()

    resp = await client.get("/api/v1/reference/sla-config")
    assert resp.status_code == 200
    assert any(item["priority"] == "CRITICAL" for item in resp.json())


@pytest.mark.asyncio
async def test_health(client):
    """Health endpoint must return 200 (DB may not be reachable in CI)."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "db" in data
