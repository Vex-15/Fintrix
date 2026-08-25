"""
API Keys management — CRUD endpoints for programmatic access keys.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User, APIKey
from app.schemas import APIKeyCreateRequest, APIKeyOut, APIKeyCreatedResponse
from app.services.auth import get_current_user, generate_api_key
from app.services.rbac import require_permission
from app.utils.audit import log_audit

router = APIRouter()


@router.post("/", response_model=APIKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: APIKeyCreateRequest,
    current_user: User = Depends(require_permission("manage_api_keys")),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a new API key. The raw key is returned ONCE and cannot be retrieved again.
    """
    raw_key, key_hash = generate_api_key()

    api_key = APIKey(
        key_prefix=raw_key[:12],
        key_hash=key_hash,
        name=body.name,
        merchant_id=current_user.merchant_id,
        scopes=body.scopes or {"read": True, "write": True},
        created_by=current_user.id if current_user.id > 0 else None,
    )
    db.add(api_key)
    await db.flush()

    await log_audit(
        db, "api_key", str(api_key.id),
        action="created",
        actor=current_user.email,
        new_state={"name": body.name, "key_prefix": raw_key[:12]},
    )

    return APIKeyCreatedResponse(
        id=api_key.id,
        raw_key=raw_key,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        scopes=api_key.scopes,
        created_at=api_key.created_at,
    )


@router.get("/", response_model=list[APIKeyOut])
async def list_api_keys(
    current_user: User = Depends(require_permission("manage_api_keys")),
    db: AsyncSession = Depends(get_db),
):
    """List all API keys for the current merchant."""
    query = select(APIKey).where(APIKey.is_active == True)
    if current_user.merchant_id:
        query = query.where(APIKey.merchant_id == current_user.merchant_id)

    result = await db.execute(query)
    return result.scalars().all()


@router.put("/{key_id}", response_model=APIKeyOut)
async def update_api_key(
    key_id: int,
    body: APIKeyCreateRequest,
    current_user: User = Depends(require_permission("manage_api_keys")),
    db: AsyncSession = Depends(get_db),
):
    """Update an API key's name or scopes."""
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    if current_user.merchant_id and api_key.merchant_id != current_user.merchant_id:
        raise HTTPException(status_code=403, detail="Cannot modify another merchant's API key")

    old_name = api_key.name
    api_key.name = body.name
    if body.scopes:
        api_key.scopes = body.scopes

    await db.flush()
    await log_audit(
        db, "api_key", str(key_id),
        action="updated",
        actor=current_user.email,
        old_state={"name": old_name},
        new_state={"name": body.name},
    )

    return api_key


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: int,
    current_user: User = Depends(require_permission("manage_api_keys")),
    db: AsyncSession = Depends(get_db),
):
    """Revoke (soft-delete) an API key."""
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    if current_user.merchant_id and api_key.merchant_id != current_user.merchant_id:
        raise HTTPException(status_code=403, detail="Cannot revoke another merchant's API key")

    api_key.is_active = False
    await db.flush()

    await log_audit(
        db, "api_key", str(key_id),
        action="revoked",
        actor=current_user.email,
    )

    return {"status": "revoked", "key_id": key_id}
