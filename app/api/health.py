from fastapi import APIRouter
from sqlalchemy import text

from app.database import AsyncSessionLocal, get_redis

router = APIRouter()


@router.get("/health")
async def health():
    checks: dict = {"status": "ok", "postgres": "ok", "redis": "ok"}

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:
        checks["postgres"] = str(exc)
        checks["status"] = "degraded"

    try:
        redis = await get_redis()
        await redis.ping()
    except Exception as exc:
        checks["redis"] = str(exc)
        checks["status"] = "degraded"

    return checks
