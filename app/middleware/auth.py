import uuid
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import select

from app.config import settings
from app.database import hash_api_key
from app.models.fragment import ApiKey


def require_admin(request: Request) -> None:
    """Dependency: validate the Admin-Key header against ADMIN_API_KEY setting."""
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is disabled. Set ADMIN_API_KEY to enable it.",
        )
    key = request.headers.get("Admin-Key", "")
    if not key or key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Admin-Key header.",
        )


async def resolve_api_key(request: Request) -> uuid.UUID:
    """
    Extract Bearer token from Authorization header, look up in DB, return app_id.
    Raises 401 if missing or invalid.
    """
    auth_header: Optional[str] = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected: Bearer <api-key>",
        )

    raw_key = auth_header.removeprefix("Bearer ").strip()
    key_hash = hash_api_key(raw_key)

    # DB session is attached to request.state by the lifespan/middleware
    db = request.state.db
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    return api_key.app_id
