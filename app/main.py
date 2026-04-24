import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import admin, health, memory, sessions
from app.database import AsyncSessionLocal, engine
from app.limiter import limiter
from app.logging_config import configure_logging

configure_logging()
logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

def _validate_env() -> None:
    from app.config import settings

    errors = []

    if settings.extraction_provider == "anthropic" and not settings.anthropic_api_key:
        errors.append("ANTHROPIC_API_KEY is required when EXTRACTION_PROVIDER=anthropic")
    if settings.extraction_provider == "openai" and not settings.openai_api_key:
        errors.append("OPENAI_API_KEY is required when EXTRACTION_PROVIDER=openai")
    if settings.embedding_provider == "openai" and not settings.openai_api_key:
        errors.append("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")

    if not settings.admin_api_key:
        logger.warning("startup.admin_disabled", hint="Set ADMIN_API_KEY to enable /admin endpoints")

    if errors:
        for err in errors:
            logger.error("startup.config_error", error=err)
        raise RuntimeError("Missing required configuration:\n" + "\n".join(f"  - {e}" for e in errors))


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_env()

    from app.config import settings
    if settings.embedding_provider == "local":
        import asyncio
        from app.extraction.embeddings import _get_local_model
        loop = asyncio.get_event_loop()
        logger.info("startup.prewarming_model", model=settings.embedding_model)
        await loop.run_in_executor(None, _get_local_model)
        logger.info("startup.model_ready")

    logger.info("startup.complete")
    yield
    await engine.dispose()
    logger.info("shutdown.complete")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ContextOS",
    description="Model-agnostic memory infrastructure for LLM applications.",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Request ID middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Per-request DB session middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    async with AsyncSessionLocal() as session:
        request.state.db = session
        response = await call_next(request)
    return response


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health.router, tags=["ops"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(memory.router, prefix="/memory", tags=["memory"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Global error handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("request.unhandled_error", error=str(exc), path=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})
