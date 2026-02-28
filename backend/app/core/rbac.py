"""
Role-based access control (RBAC) dependency factory.

Usage:
    @router.get("/admin-only")
    async def admin_endpoint(user = Depends(require_role("ADMIN"))):
        ...

    @router.get("/dispatchers-and-admins")
    async def multi_role_endpoint(user = Depends(require_role("ADMIN", "DISPATCHER"))):
        ...
"""
from fastapi import Depends, HTTPException, status

from app.core.security import get_current_user


def require_role(*roles: str):
    """
    Dependency factory that enforces the caller's role is in *roles.
    Accepts any authenticated user when called with no role arguments.
    """

    async def _check_role(current_user=Depends(get_current_user)):
        if roles and current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {list(roles)}",
            )
        return current_user

    return _check_role
