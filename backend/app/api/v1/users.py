"""
User management endpoints.

All routes (except /me) require ADMIN role.
Cognito integration is conditional: if COGNITO_USER_POOL_ID is not configured
(e.g. in development), Cognito calls are skipped gracefully.
"""
import logging
import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.rbac import require_role
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.user import UserCreate, UserListResponse, UserResponse, UserUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])
settings = get_settings()

# ---------------------------------------------------------------------------
# Cognito helpers (no-op when Cognito is not configured)
# ---------------------------------------------------------------------------

def _cognito_client():
    """Return a boto3 Cognito IDP client, or None if not configured."""
    if not settings.cognito_configured:
        return None
    try:
        import boto3
        return boto3.client("cognito-idp", region_name=settings.aws_region)
    except Exception as exc:
        logger.warning("Failed to create Cognito client: %s", exc)
        return None


def _cognito_create_user(client, email: str, full_name: str) -> str | None:
    """
    Call AdminCreateUser and return the Cognito sub.
    Returns None if client is not available (dev mode).
    """
    if client is None:
        return None
    try:
        resp = client.admin_create_user(
            UserPoolId=settings.cognito_user_pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "name", "Value": full_name},
            ],
            DesiredDeliveryMediums=["EMAIL"],
        )
        return resp["User"]["Attributes"][0]["Value"]  # sub
    except client.exceptions.UsernameExistsException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists in Cognito",
        ) from exc
    except Exception as exc:
        logger.error("Cognito AdminCreateUser failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create user in authentication system",
        ) from exc


def _cognito_add_to_group(client, email: str, role: str) -> None:
    if client is None:
        return
    try:
        client.admin_add_user_to_group(
            UserPoolId=settings.cognito_user_pool_id,
            Username=email,
            GroupName=role,
        )
    except Exception as exc:
        logger.warning("Failed to add user to Cognito group %s: %s", role, exc)


def _cognito_reset_password(client, email: str) -> None:
    if client is None:
        return
    try:
        client.admin_reset_user_password(
            UserPoolId=settings.cognito_user_pool_id,
            Username=email,
        )
    except Exception as exc:
        logger.warning("Failed to reset Cognito password for %s: %s", email, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to trigger password reset in authentication system",
        ) from exc


def _cognito_disable_user(client, email: str) -> None:
    if client is None:
        return
    try:
        client.admin_disable_user(
            UserPoolId=settings.cognito_user_pool_id,
            Username=email,
        )
    except Exception as exc:
        logger.warning("Failed to disable Cognito user %s: %s", email, exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the authenticated user's own profile."""
    return UserResponse.model_validate(current_user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("ADMIN")),
) -> UserResponse:
    """Create a new user. Triggers Cognito AdminCreateUser (when configured)."""
    # Check duplicate email in DB
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    client = _cognito_client()
    cognito_sub = _cognito_create_user(client, payload.email, payload.full_name)

    # In dev mode (no Cognito), generate a synthetic sub
    if cognito_sub is None:
        cognito_sub = str(uuid.uuid4())

    user = User(
        cognito_user_id=cognito_sub,
        full_name=payload.full_name,
        email=payload.email,
        role=payload.role,
        responsible_province=payload.responsible_province,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    _cognito_add_to_group(client, payload.email, payload.role)

    logger.info("Created user %s (role=%s, cognito=%s)", user.id, user.role, cognito_sub)
    return UserResponse.model_validate(user)


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("ADMIN")),
) -> UserListResponse:
    """List all users with pagination."""
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    total_result = await db.execute(select(func.count()).select_from(User))
    total = total_result.scalar_one()

    result = await db.execute(select(User).offset(offset).limit(page_size))
    users = result.scalars().all()

    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("ADMIN")),
) -> UserResponse:
    """Get a single user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("ADMIN")),
) -> UserResponse:
    """Update user fields (name, role, province, active status)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.role is not None:
        user.role = payload.role
    if payload.responsible_province is not None:
        user.responsible_province = payload.responsible_province
    if payload.is_active is not None:
        was_active = user.is_active
        user.is_active = payload.is_active
        # Disable in Cognito when deactivating
        if was_active and not payload.is_active and user.email:
            client = _cognito_client()
            _cognito_disable_user(client, user.email)

    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("ADMIN")),
) -> None:
    """Trigger a Cognito password reset email for the user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no email address",
        )

    client = _cognito_client()
    if client is not None:
        _cognito_reset_password(client, user.email)
    else:
        logger.info(
            "DEV: password reset skipped for %s (Cognito not configured)", user.email
        )
