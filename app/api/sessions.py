import asyncio
import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy import select

from app.extraction import get_extractor
from app.extraction.embeddings import embed_batch
from app.limiter import limiter
from app.middleware.auth import resolve_api_key
from app.models.fragment import DeadLetterSession, Fragment
from app.schemas.session import SessionCreate, SessionResponse

logger = structlog.get_logger(__name__)
router = APIRouter()

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds; delay doubles each attempt
DEDUP_THRESHOLD = 0.95       # cosine similarity ≥ this → exact duplicate, skip
CONSOLIDATION_LOW = 0.75     # cosine similarity in [0.75, 0.95) → near-match, consolidate

# Similarity zones:
#   ≥ DEDUP_THRESHOLD           → duplicate (skip)
#   ≥ CONSOLIDATION_LOW         → near-match (supersede old, store new with max importance)
#   < CONSOLIDATION_LOW         → new info (store as fresh fragment)


async def _closest_active_fragment(
    db, app_id: uuid.UUID, user_id: str, fragment_type: str, embedding: list[float]
) -> tuple[float, "Fragment | None"]:
    """Return (similarity, fragment) for the nearest active fragment of the same type, or (0.0, None).

    Scoped to fragment_type to prevent cross-type supersession (e.g., a 'preference'
    fragment should never supersede a 'fact' fragment even if semantically close).
    """
    distance_col = Fragment.embedding.cosine_distance(embedding).label("distance")
    stmt = (
        select(Fragment, distance_col)
        .where(Fragment.app_id == app_id)
        .where(Fragment.user_id == user_id)
        .where(Fragment.type == fragment_type)
        .where(Fragment.embedding.isnot(None))
        .where(Fragment.superseded_by_id.is_(None))
        .order_by(distance_col)
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        return 0.0, None
    frag, distance = row
    return max(0.0, 1.0 - float(distance)), frag


async def _run_extraction(
    conversation: str,
    app_id: uuid.UUID,
    user_id: str,
    session_id: str,
    source_client: str | None,
    metadata: dict,
    db_session_factory,
) -> None:
    """Background task: extract fragments with retry, dedup, persist. Dead-letter on exhaustion."""
    log = logger.bind(session_id=session_id, user_id=user_id, app_id=str(app_id))
    extractor = get_extractor()
    last_error: str = ""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw_fragments = await extractor.extract(conversation)

            if not raw_fragments:
                log.info("extraction.empty", attempt=attempt)
                return

            contents = [f.content for f in raw_fragments]
            embeddings = await embed_batch(contents)

            stored = 0
            skipped = 0
            consolidated = 0
            async with db_session_factory() as db:
                for raw, embedding in zip(raw_fragments, embeddings):
                    similarity, closest = await _closest_active_fragment(db, app_id, user_id, raw.type, embedding)

                    if similarity >= DEDUP_THRESHOLD:
                        # Exact duplicate — nothing new to learn
                        skipped += 1
                        continue

                    # Build the new fragment (importance = max of incoming and any superseded fragment)
                    inherited_importance = max(raw.importance, closest.importance if closest and similarity >= CONSOLIDATION_LOW else raw.importance)
                    fragment = Fragment(
                        app_id=app_id,
                        user_id=user_id,
                        content=raw.content,
                        embedding=embedding,
                        type=raw.type,
                        importance=inherited_importance,
                        source_client=source_client,
                        created_at=datetime.utcnow(),
                        metadata_=metadata,
                    )
                    db.add(fragment)

                    if similarity >= CONSOLIDATION_LOW and closest is not None:
                        # Near-match: flush to get the new fragment's ID, then supersede the old one
                        await db.flush()
                        closest.superseded_by_id = fragment.id
                        consolidated += 1
                    else:
                        stored += 1

                await db.commit()

            log.info(
                "extraction.complete",
                stored=stored,
                consolidated=consolidated,
                skipped_duplicates=skipped,
                attempt=attempt,
            )
            return

        except Exception as exc:
            last_error = str(exc)
            log.warning("extraction.failed", attempt=attempt, max_retries=MAX_RETRIES, error=last_error)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))

    # All retries exhausted — write to dead-letter
    log.error("extraction.dead_letter", attempts=MAX_RETRIES, error=last_error)
    async with db_session_factory() as db:
        dead = DeadLetterSession(
            session_id=session_id,
            app_id=app_id,
            user_id=user_id,
            conversation=conversation,
            source_client=source_client,
            error=last_error,
            attempts=MAX_RETRIES,
            failed_at=datetime.utcnow(),
            metadata_=metadata,
        )
        db.add(dead)
        await db.commit()


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=SessionResponse)
@limiter.limit("60/minute")
async def create_session(
    payload: SessionCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    app_id: uuid.UUID = Depends(resolve_api_key),
):
    from app.database import AsyncSessionLocal

    session_id = str(uuid.uuid4())
    log = logger.bind(session_id=session_id, user_id=payload.user_id, app_id=str(app_id))
    log.info("session.accepted", source_client=payload.source_client)

    background_tasks.add_task(
        _run_extraction,
        conversation=payload.conversation,
        app_id=app_id,
        user_id=payload.user_id,
        session_id=session_id,
        source_client=payload.source_client,
        metadata={**payload.metadata, "session_id": session_id},
        db_session_factory=AsyncSessionLocal,
    )

    return SessionResponse(
        session_id=session_id,
        user_id=payload.user_id,
        status="accepted",
        message="Conversation received. Memory extraction is running in the background.",
    )
