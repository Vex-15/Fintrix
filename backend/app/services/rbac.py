"""
RBAC service — role-based access control for Fintrix.

Roles:
  - admin: Full access (user management, API keys, settings, all operations)
  - operator: Read + write operations (reconciliation, exceptions, investigations)
  - viewer: Read-only access (dashboard, view exceptions, audit trail)
"""

from fastapi import Depends, HTTPException, status
from app.models import User
from app.services.auth import get_current_user


# ---------------------------------------------------------------------------
# Permission Matrix
# ---------------------------------------------------------------------------

# Maps role → set of allowed permissions
ROLE_PERMISSIONS = {
    "admin": {
        "read", "write", "delete",
        "manage_users", "manage_api_keys", "manage_settings",
        "run_reconciliation", "investigate", "resolve_exceptions",
        "export_data", "view_audit", "manage_scheduler",
        "manage_merchants", "bulk_actions",
    },
    "operator": {
        "read", "write",
        "run_reconciliation", "investigate", "resolve_exceptions",
        "export_data", "view_audit", "bulk_actions",
    },
    "viewer": {
        "read",
        "view_audit",
    },
}


def has_permission(role: str, permission: str) -> bool:
    """Check if a role has a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())


# ---------------------------------------------------------------------------
# FastAPI Dependencies
# ---------------------------------------------------------------------------

def require_role(*allowed_roles: str):
    """
    Dependency factory: creates a dependency that checks if the current user
    has one of the allowed roles.

    Usage:
        @router.post("/admin-only", dependencies=[Depends(require_role("admin"))])
        async def admin_endpoint(): ...
    """
    async def _check_role(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role(s): {', '.join(allowed_roles)}. Your role: {current_user.role}",
            )
        return current_user
    return _check_role


def require_permission(permission: str):
    """
    Dependency factory: checks if the current user's role has a specific permission.

    Usage:
        @router.post("/export", dependencies=[Depends(require_permission("export_data"))])
        async def export(): ...
    """
    async def _check_permission(current_user: User = Depends(get_current_user)):
        if not has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: '{permission}' required. Your role: {current_user.role}",
            )
        return current_user
    return _check_permission
