"""
Tests for user management endpoints.

Uses the test client fixture from conftest.py which runs with DEV_SKIP_AUTH=true.
The default user is admin_user (ADMIN role).
"""
import uuid

import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_get_me(client, admin_user):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == admin_user.email
    assert data["role"] == "ADMIN"


@pytest.mark.asyncio
async def test_create_user_valid(client):
    payload = {
        "full_name": "New Officer",
        "email": "new.officer@test.local",
        "role": "OFFICER",
        "responsible_province": "เชียงใหม่",
    }
    resp = await client.post("/api/v1/users", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["full_name"] == "New Officer"
    assert data["role"] == "OFFICER"
    assert data["responsible_province"] == "เชียงใหม่"
    assert data["is_active"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_create_user_duplicate_email(client, admin_user):
    """Creating a user with an email that already exists returns 409."""
    payload = {
        "full_name": "Duplicate",
        "email": admin_user.email,  # same as admin
        "role": "DISPATCHER",
    }
    resp = await client.post("/api/v1/users", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_users_admin(client, admin_user):
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_users_officer_forbidden(client, officer_user):
    """OFFICER must receive 403 on the user list endpoint."""
    resp = await client.get(
        "/api/v1/users",
        headers={"X-Dev-User-ID": officer_user.cognito_user_id},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_user_by_id(client, admin_user):
    resp = await client.get(f"/api/v1/users/{admin_user.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(admin_user.id)


@pytest.mark.asyncio
async def test_get_user_not_found(client):
    resp = await client.get(f"/api/v1/users/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_user(client, officer_user):
    payload = {"full_name": "Updated Name", "is_active": True}
    resp = await client.put(f"/api/v1/users/{officer_user.id}", json=payload)
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_deactivate_user(client, officer_user):
    """Setting is_active=false should persist in DB."""
    resp = await client.put(
        f"/api/v1/users/{officer_user.id}", json={"is_active": False}
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_reset_password_no_cognito(client, officer_user):
    """
    Without Cognito configured the endpoint still returns 204
    (Cognito call is skipped in dev mode).
    """
    resp = await client.post(f"/api/v1/users/{officer_user.id}/reset-password")
    assert resp.status_code == 204
