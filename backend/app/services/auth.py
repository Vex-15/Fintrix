"""
Authentication service — password hashing, JWT tokens, user dependencies.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.models import User, APIKey

import hashlib
import secrets

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer token scheme
bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Password Utilities
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT Token Utilities
# ---------------------------------------------------------------------------

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a long-lived refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.refresh_token_expire_days)
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# API Key Utilities
# ---------------------------------------------------------------------------

def generate_api_key() -> tuple[str, str]:
    """
    Generate an API key and its hash.
    Returns: (raw_key, key_hash)
    The raw_key is shown once to the user; key_hash is stored in the DB.
    """
    raw_key = f"ftx_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, key_hash


def hash_api_key(raw_key: str) -> str:
    """Hash an API key for lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# FastAPI Dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get the current authenticated user from JWT token or API key.
    Supports both Bearer token and X-API-Key header.
    """
    # DEMO MODE bypass
    if settings.demo_mode:
        result = await db.execute(select(User).where(User.email == settings.default_admin_email))
        user = result.scalar_one_or_none()
        if user:
            return user
        # Fallback if admin not created yet
        return User(id=1, email=settings.default_admin_email, name="Demo Admin", role="admin", is_active=True)

    # Try API key first
    api_key_header = request.headers.get("X-API-Key") if request else None
    if api_key_header:
        return await _authenticate_api_key(db, api_key_header)

    # Try Bearer token
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide Bearer token or X-API-Key header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Use an access token.",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
        )

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
        )

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Get the current user if authenticated, otherwise return None.
    Used for endpoints that work with or without auth.
    """
    # DEMO MODE bypass
    if settings.demo_mode:
        result = await db.execute(select(User).where(User.email == settings.default_admin_email))
        user = result.scalar_one_or_none()
        if user:
            return user
        return User(id=1, email=settings.default_admin_email, name="Demo Admin", role="admin", is_active=True)

    try:
        return await get_current_user(credentials, request, db)
    except HTTPException:
        return None


async def _authenticate_api_key(db: AsyncSession, raw_key: str) -> User:
    """Authenticate via API key and return the associated user (or a synthetic user)."""
    key_hash = hash_api_key(raw_key)
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active == True)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    # Check expiry
    if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired.",
        )

    # Update last used
    api_key.last_used_at = datetime.now(timezone.utc)
    await db.flush()

    # If created_by is set, return that user
    if api_key.created_by:
        result = await db.execute(select(User).where(User.id == api_key.created_by))
        user = result.scalar_one_or_none()
        if user:
            return user

    # Create a synthetic user for API key access
    synthetic = User(
        id=-1,
        email=f"apikey:{api_key.key_prefix}",
        hashed_password="",
        name=f"API Key: {api_key.name}",
        role="operator",
        merchant_id=api_key.merchant_id,
        is_active=True,
    )
    return synthetic


async def ensure_default_admin(db: AsyncSession):
    """Create default admin user and merchant on first startup if they don't exist."""
    # Check if any user exists
    result = await db.execute(select(User).limit(1))
    if result.scalar_one_or_none():
        return  # Users exist, skip

    # Create default merchant
    from app.models import Merchant
    default_merchant = Merchant(
        id="merchant_default",
        name="Fintrix Demo",
    )
    db.add(default_merchant)

    # Create default admin
    admin = User(
        email=settings.default_admin_email,
        hashed_password=hash_password(settings.default_admin_password),
        name="Admin",
        role="admin",
        merchant_id="merchant_default",
    )
    db.add(admin)
    await db.flush()
    await db.commit()
    print(f"[OK] Default admin created: {settings.default_admin_email}")
