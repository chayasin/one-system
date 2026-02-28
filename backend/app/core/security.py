"""
Cognito JWT verification + current-user dependency.

In development with DEV_SKIP_AUTH=true:
  - Pass X-Dev-User-ID: <uuid> header to authenticate as that user.
  - If the header is absent, the first admin user in the DB is used as fallback
    (only in development; production always requires a valid token).

In production / staging:
  - Bearer token must be a valid Cognito access_token.
  - JWKS fetched once from Cognito and cached for JWKS_CACHE_TTL seconds.
"""
import logging
import time
from typing import Any
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwk, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db

logger = logging.getLogger(__name__)
settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

# ---------------------------------------------------------------------------
# JWKS cache
# ---------------------------------------------------------------------------
_jwks_cache: dict[str, Any] = {}  # kid → JWK key
_jwks_fetched_at: float = 0.0


async def _get_jwks() -> dict[str, Any]:
    """Fetch and cache Cognito JWKS.  Returns {kid: jwk_key} mapping."""
    global _jwks_cache, _jwks_fetched_at

    now = time.monotonic()
    if _jwks_cache and (now - _jwks_fetched_at) < settings.jwks_cache_ttl:
        return _jwks_cache

    if not settings.cognito_configured:
        return {}

    region = settings.aws_region
    pool_id = settings.cognito_user_pool_id
    jwks_url = (
        f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(jwks_url)
            resp.raise_for_status()
            keys = resp.json().get("keys", [])
            _jwks_cache = {k["kid"]: k for k in keys}
            _jwks_fetched_at = now
            logger.info("Fetched %d keys from Cognito JWKS", len(_jwks_cache))
    except Exception as exc:
        logger.error("Failed to fetch Cognito JWKS: %s", exc)
        # Return stale cache if available
        if _jwks_cache:
            return _jwks_cache
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    return _jwks_cache


def _verify_cognito_jwt(token: str, jwks: dict[str, Any]) -> dict[str, Any]:
    """
    Decode and verify a Cognito access_token.
    Raises HTTPException(401) on any failure.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token header") from exc

    kid = unverified_header.get("kid")
    if kid not in jwks:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token key not found")

    key = jwk.construct(jwks[kid])

    region = settings.aws_region
    pool_id = settings.cognito_user_pool_id
    issuer = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Cognito access tokens have no audience
        )
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired") from exc
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token verification failed") from exc

    if payload.get("iss") != issuer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token issuer")

    if payload.get("token_use") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expected access token")

    return payload


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    FastAPI dependency: resolve and return the current authenticated User ORM object.

    Dev bypass: when DEV_SKIP_AUTH=true (development only), authentication is
    skipped and a User row from the DB is returned based on the X-Dev-User-ID
    header (or the first admin user if the header is absent).
    """
    # Import here to avoid circular imports
    from app.models.user import User

    # ------------------------------------------------------------------ #
    # Development bypass
    # ------------------------------------------------------------------ #
    if settings.auth_disabled:
        # Look for X-Dev-User-ID header (injected by _inject_dev_header below)
        # We use a context var set by the dev auth middleware
        cognito_sub = _dev_cognito_sub.get(None)
        if cognito_sub:
            result = await db.execute(select(User).where(User.cognito_user_id == cognito_sub))
            user = result.scalars().first()
        else:
            # Fall back to first admin
            result = await db.execute(
                select(User).where(User.role == "ADMIN", User.is_active.is_(True)).limit(1)
            )
            user = result.scalars().first()

        if user:
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Dev auth: no matching user found. "
                   "Set X-Dev-User-ID header or create an admin user first.",
        )

    # ------------------------------------------------------------------ #
    # Production: Cognito JWT
    # ------------------------------------------------------------------ #
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not settings.cognito_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this server",
        )

    jwks = await _get_jwks()
    payload = _verify_cognito_jwt(token, jwks)
    cognito_sub = payload.get("sub")

    result = await db.execute(select(User).where(User.cognito_user_id == cognito_sub))
    user = result.scalars().first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


# ---------------------------------------------------------------------------
# Context variable for dev-mode user injection (set by middleware)
# ---------------------------------------------------------------------------
from contextvars import ContextVar

_dev_cognito_sub: ContextVar[str | None] = ContextVar("_dev_cognito_sub", default=None)


def set_dev_cognito_sub(cognito_sub: str | None) -> None:
    _dev_cognito_sub.set(cognito_sub)
