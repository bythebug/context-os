"""
Admin API — app management, key rotation, usage, GDPR bulk delete.

All endpoints require the Admin-Key header matching ADMIN_API_KEY in settings.
"""
import secrets
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_redis, hash_api_key
from app.middleware.auth import require_admin
from app.models.fragment import ApiKey, App, DeadLetterSession, Fragment
from app.schemas.admin import ApiKeyOut, AppCreate, AppOut, AppUsage

logger = structlog.get_logger(__name__)
router = APIRouter(dependencies=[Depends(require_admin)])


# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------

@router.post("/apps", response_model=AppOut, status_code=status.HTTP_201_CREATED)
async def create_app(
    payload: AppCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new app."""
    app = App(name=payload.name)
    db.add(app)
    await db.commit()
    await db.refresh(app)
    logger.info("admin.app.created", app_id=str(app.id), name=app.name)
    return app


@router.get("/apps", response_model=list[AppOut])
async def list_apps(db: AsyncSession = Depends(get_db)):
    """List all apps."""
    result = await db.execute(select(App).order_by(App.created_at.desc()))
    return result.scalars().all()


@router.get("/apps/{app_id}", response_model=AppOut)
async def get_app(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a single app by ID."""
    app = await _get_app_or_404(db, app_id)
    return app


@router.delete("/apps/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_app(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Delete an app and all its data (fragments, keys, dead-letter records).
    Cascades via FK constraints.
    """
    app = await _get_app_or_404(db, app_id)
    await db.delete(app)
    await db.commit()
    logger.info("admin.app.deleted", app_id=str(app_id))


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

@router.get("/apps/{app_id}/keys", response_model=list[ApiKeyOut])
async def list_keys(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """List all API keys for an app (hashes only — raw keys are never stored)."""
    await _get_app_or_404(db, app_id)
    result = await db.execute(
        select(ApiKey).where(ApiKey.app_id == app_id).order_by(ApiKey.created_at.desc())
    )
    return result.scalars().all()


@router.post("/apps/{app_id}/keys", response_model=ApiKeyOut, status_code=status.HTTP_201_CREATED)
async def rotate_key(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Issue a new API key for an app (key rotation).
    The raw key is returned once — store it immediately.
    """
    await _get_app_or_404(db, app_id)
    raw_key = "sk-" + secrets.token_urlsafe(32)
    api_key = ApiKey(app_id=app_id, key_hash=hash_api_key(raw_key))
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    logger.info("admin.key.rotated", app_id=str(app_id), key_id=str(api_key.id))
    # Inject raw key into response — only time it's ever visible
    out = ApiKeyOut.model_validate(api_key)
    out.key = raw_key
    return out


@router.delete("/apps/{app_id}/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(
    app_id: uuid.UUID,
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Revoke a specific API key."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.app_id == app_id)
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found.")
    await db.delete(key)
    await db.commit()
    logger.info("admin.key.deleted", app_id=str(app_id), key_id=str(key_id))


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

@router.get("/apps/{app_id}/usage", response_model=AppUsage)
async def get_usage(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Return fragment count, unique users, dead-letter count, and last active time."""
    app = await _get_app_or_404(db, app_id)

    frag_stats = await db.execute(
        select(
            func.count(Fragment.id).label("total"),
            func.count(func.distinct(Fragment.user_id)).label("unique_users"),
            func.max(Fragment.created_at).label("last_active"),
        ).where(Fragment.app_id == app_id)
    )
    row = frag_stats.one()

    dead_count = await db.scalar(
        select(func.count(DeadLetterSession.id)).where(DeadLetterSession.app_id == app_id)
    )

    return AppUsage(
        app_id=app_id,
        app_name=app.name,
        total_fragments=row.total or 0,
        total_dead_letters=dead_count or 0,
        unique_users=row.unique_users or 0,
        last_active=row.last_active,
    )


# ---------------------------------------------------------------------------
# GDPR bulk delete
# ---------------------------------------------------------------------------

@router.delete("/memory", status_code=status.HTTP_200_OK)
async def bulk_delete_user(
    user_id: str = Query(..., description="Delete all memory for this user across all apps."),
    app_id: uuid.UUID = Query(default=None, description="Scope deletion to a single app."),
    db: AsyncSession = Depends(get_db),
):
    """
    GDPR bulk delete — wipe all fragments (and dead-letter records) for a user.
    Optionally scoped to a single app with ?app_id=...
    Invalidates all Redis cache entries for this user.
    """
    conditions = [Fragment.user_id == user_id]
    dl_conditions = [DeadLetterSession.user_id == user_id]
    if app_id:
        conditions.append(Fragment.app_id == app_id)
        dl_conditions.append(DeadLetterSession.app_id == app_id)

    frag_result: CursorResult = await db.execute(delete(Fragment).where(*conditions))  # type: ignore[assignment]
    dl_result: CursorResult = await db.execute(delete(DeadLetterSession).where(*dl_conditions))  # type: ignore[assignment]
    await db.commit()

    deleted_fragments = frag_result.rowcount or 0
    deleted_dl = dl_result.rowcount or 0

    # Best-effort Redis cache invalidation (pattern scan)
    try:
        redis = await get_redis()
        cursor = 0
        deleted_keys = 0
        while True:
            cursor, keys = await redis.scan(cursor, match="memory:*", count=100)
            if keys:
                await redis.delete(*keys)
                deleted_keys += len(keys)
            if cursor == 0:
                break
    except Exception:
        pass  # cache invalidation is best-effort

    logger.info(
        "admin.gdpr.bulk_delete",
        user_id=user_id,
        app_id=str(app_id) if app_id else "all",
        deleted_fragments=deleted_fragments,
        deleted_dead_letters=deleted_dl,
        invalidated_cache_keys=deleted_keys,
    )

    return {
        "user_id": user_id,
        "deleted_fragments": deleted_fragments,
        "deleted_dead_letters": deleted_dl,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_app_or_404(db: AsyncSession, app_id: uuid.UUID) -> App:
    result = await db.execute(select(App).where(App.id == app_id))
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found.")
    return app
