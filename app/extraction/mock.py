"""
Mock extractor for local testing — no API key required.
Returns a small set of hardcoded fragments derived from simple keyword
matching so the full pipeline (write → embed → store → retrieve) can be
verified without any external API calls.

Activate with: EXTRACTION_PROVIDER=mock
"""
from app.extraction.base import BaseExtractor, RawFragment

_KEYWORD_FRAGMENTS: list[tuple[list[str], RawFragment]] = [
    (
        ["fastapi", "api", "rest", "endpoint"],
        RawFragment(content="User is building a FastAPI REST service", type="project", importance=4),
    ),
    (
        ["pgvector", "postgres", "vector", "embedding"],
        RawFragment(content="User is using pgvector for vector storage", type="decision", importance=4),
    ),
    (
        ["async", "asyncio", "await"],
        RawFragment(content="User prefers async Python patterns", type="preference", importance=3),
    ),
    (
        ["fly", "fly.io", "deploy", "deployment", "infrastructure"],
        RawFragment(content="User decided to deploy on Fly.io", type="decision", importance=3),
    ),
    (
        ["openai", "anthropic", "claude", "gpt", "llm", "model"],
        RawFragment(content="User is building an LLM application", type="fact", importance=3),
    ),
    (
        ["redis", "cache"],
        RawFragment(content="User is using Redis for caching", type="fact", importance=2),
    ),
]

# Always included so there's always at least one fragment
_DEFAULT_FRAGMENT = RawFragment(
    content="User is working on a software project",
    type="fact",
    importance=1,
)


class MockExtractor(BaseExtractor):
    async def extract(self, conversation: str) -> list[RawFragment]:
        lower = conversation.lower()
        matched = [
            frag
            for keywords, frag in _KEYWORD_FRAGMENTS
            if any(kw in lower for kw in keywords)
        ]
        return matched if matched else [_DEFAULT_FRAGMENT]
