import hashlib
import json
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

import structlog

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, get_redis
from app.extraction.embeddings import embed
from app.limiter import limiter
from app.middleware.auth import resolve_api_key
from app.models.fragment import Fragment
from app.schemas.memory import FragmentOut, MemoryMeta, MemoryResponse

CACHE_TTL = 60         # seconds
DECAY_HALF_LIFE = 30.0 # days — fragment relevance halves every 30 days
RRF_K = 60             # Reciprocal Rank Fusion constant (standard value)
HYBRID_FETCH_N = 3     # fetch top_k * HYBRID_FETCH_N from each retrieval path before fusion

logger = structlog.get_logger(__name__)
router = APIRouter()


def _decay_score(created_at: datetime) -> float:
    """Exponential decay: 1.0 at creation, ~0.5 at DECAY_HALF_LIFE days."""
    age_days = (datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)).days
    return math.exp(-math.log(2) * age_days / DECAY_HALF_LIFE)


def _build_prompt_block(fragments: list[tuple[Fragment, float]]) -> str:
    if not fragments:
        return ""
    lines = ["Relevant context about this user:"]
    for frag, score in fragments:
        lines.append(f"- [{frag.type}] {frag.content} (relevance: {score:.2f})")
    return "\n".join(lines)


def _cache_key(app_id: uuid.UUID, user_id: str, q: str, top_k: int, scope: str, type_filter: Optional[str]) -> str:
    raw = f"{app_id}:{user_id}:{q}:{top_k}:{scope}:{type_filter}"
    return "memory:" + hashlib.sha256(raw.encode()).hexdigest()


@router.get("", response_model=MemoryResponse)
@limiter.limit("120/minute")
async def query_memory(
    request: Request,
    user_id: str = Query(..., description="User identifier"),
    q: str = Query(..., description="Query string to match against stored fragments"),
    top_k: int = Query(default=None, ge=1, le=50),
    scope: Optional[Literal["app", "global"]] = Query(
        default="global",
        description="'global' returns fragments across all source clients (default). 'app' restricts to this app_id.",
    ),
    type_filter: Optional[str] = Query(
        default=None,
        alias="type",
        description="Filter by fragment type: fact | preference | decision | event | project",
    ),
    db: AsyncSession = Depends(get_db),
    app_id: uuid.UUID = Depends(resolve_api_key),
):
    start_ms = time.monotonic()
    k = top_k or settings.default_top_k
    cache_key = _cache_key(app_id, user_id, q, k, scope or "global", type_filter)

    # Check Redis cache
    try:
        redis = await get_redis()
        cached = await redis.get(cache_key)
        if cached:
            logger.info("memory.cache_hit", user_id=user_id)
            return MemoryResponse(**json.loads(cached))
    except Exception:
        logger.warning("memory.cache_unavailable")

    # Embed the query
    query_embedding = await embed(q)

    # Build filter conditions (active fragments only — exclude superseded)
    conditions = [
        Fragment.user_id == user_id,
        Fragment.superseded_by_id.is_(None),
    ]
    if scope == "app":
        conditions.append(Fragment.app_id == app_id)
    if type_filter:
        conditions.append(Fragment.type == type_filter)

    fetch_n = k * HYBRID_FETCH_N

    # --- Vector search (pgvector cosine distance) ---
    distance_col = Fragment.embedding.cosine_distance(query_embedding).label("distance")
    vec_stmt = (
        select(Fragment, distance_col)
        .where(and_(*conditions))
        .where(Fragment.embedding.isnot(None))
        .order_by(distance_col)
        .limit(fetch_n)
    )
    vec_rows = (await db.execute(vec_stmt)).all()

    # --- BM25 text search (Postgres tsvector / ts_rank_cd) ---
    tsquery = func.plainto_tsquery("english", q)
    ts_rank_col = func.ts_rank_cd(
        func.to_tsvector("english", Fragment.content), tsquery
    ).label("ts_rank")
    fts_stmt = (
        select(Fragment, ts_rank_col)
        .where(and_(*conditions))
        .where(func.to_tsvector("english", Fragment.content).op("@@")(tsquery))
        .order_by(ts_rank_col.desc())
        .limit(fetch_n)
    )
    fts_rows = (await db.execute(fts_stmt)).all()

    # --- Reciprocal Rank Fusion ---
    # rrf_scores: {frag_id: (fragment, rrf_score, cosine_similarity)}
    rrf_scores: dict[uuid.UUID, tuple[Fragment, float, float]] = {}

    for rank, (frag, distance) in enumerate(vec_rows, 1):
        sim = max(0.0, 1.0 - float(distance))
        rrf_scores[frag.id] = (frag, 1.0 / (RRF_K + rank), sim)

    for rank, (frag, _ts_rank) in enumerate(fts_rows, 1):
        rrf_boost = 1.0 / (RRF_K + rank)
        if frag.id in rrf_scores:
            old_frag, old_rrf, old_sim = rrf_scores[frag.id]
            rrf_scores[frag.id] = (old_frag, old_rrf + rrf_boost, old_sim)
        else:
            # Only in BM25 results (no vector match in top fetch_n)
            rrf_scores[frag.id] = (frag, rrf_boost, 0.0)

    # Sort by RRF score, take top k
    rrf_ranked = sorted(rrf_scores.values(), key=lambda x: x[1], reverse=True)[:k]

    # --- Re-rank with importance + decay (on the RRF candidate set) ---
    scored: list[tuple[Fragment, float]] = []
    for frag, _rrf, similarity in rrf_ranked:
        decay = _decay_score(frag.created_at)
        # Composite score: similarity 50%, importance 30%, recency decay 20%
        final_score = similarity * 0.5 + (frag.importance / 5.0) * 0.3 + decay * 0.2
        scored.append((frag, final_score))

    scored.sort(key=lambda x: x[1], reverse=True)

    elapsed_ms = int((time.monotonic() - start_ms) * 1000)

    fragments_out = [
        FragmentOut(
            id=frag.id,
            content=frag.content,
            type=frag.type,
            importance=frag.importance,
            source_client=frag.source_client,
            score=round(score, 4),
            created_at=frag.created_at,
        )
        for frag, score in scored
    ]

    response = MemoryResponse(
        user_id=user_id,
        fragments=fragments_out,
        prompt_block=_build_prompt_block(scored),
        meta=MemoryMeta(total_fragments=len(fragments_out), query_ms=elapsed_ms),
    )

    # Write to cache (best-effort)
    try:
        redis = await get_redis()
        await redis.set(cache_key, response.model_dump_json(), ex=CACHE_TTL)
    except Exception:
        pass

    return response


@router.delete("/{fragment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fragment(
    fragment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    app_id: uuid.UUID = Depends(resolve_api_key),
):
    result = await db.execute(
        select(Fragment).where(
            Fragment.id == fragment_id,
            Fragment.app_id == app_id,  # scoped — can only delete own app's fragments
        )
    )
    fragment = result.scalar_one_or_none()
    if fragment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fragment not found.")

    await db.delete(fragment)
    await db.commit()
    logger.info("fragment.deleted", fragment_id=str(fragment_id), app_id=str(app_id))
