"""
Embedding provider abstraction.

EMBEDDING_PROVIDER=local  — sentence-transformers (all-MiniLM-L6-v2, 384 dims, no API key)
EMBEDDING_PROVIDER=openai — OpenAI text-embedding-3-small (1536 dims, requires OPENAI_API_KEY)
"""
import asyncio
import logging
from functools import lru_cache

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Local (sentence-transformers)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_local_model():
    from sentence_transformers import SentenceTransformer
    logger.info("Loading local embedding model: %s", settings.embedding_model)
    return SentenceTransformer(settings.embedding_model)


async def _embed_local(texts: list[str]) -> list[list[float]]:
    loop = asyncio.get_event_loop()
    model = _get_local_model()
    # Run in executor to avoid blocking the event loop
    vectors = await loop.run_in_executor(None, lambda: model.encode(texts, convert_to_numpy=True))
    return [v.tolist() for v in vectors]


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def _get_openai_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=settings.openai_api_key)


_openai_client = None


async def _embed_openai(texts: list[str]) -> list[list[float]]:
    global _openai_client
    if _openai_client is None:
        _openai_client = _get_openai_client()
    response = await _openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
        dimensions=settings.embedding_dimensions,
    )
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def embed(text: str) -> list[float]:
    results = await embed_batch([text])
    return results[0]


async def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if settings.embedding_provider == "openai":
        return await _embed_openai(texts)
    return await _embed_local(texts)
