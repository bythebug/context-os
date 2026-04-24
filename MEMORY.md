# ContextOS — AI Agent Memory

This file is the authoritative context for any AI agent (or human) continuing work on this project.
Read this before reading anything else. Update it after completing any meaningful work.

---

## What this project is

ContextOS is a model-agnostic memory infrastructure REST API for LLM applications.
The core idea: decouple memory from the model. Any AI client (Claude, GPT, custom agents)
calls two endpoints — write after a session, query before the next LLM call. ContextOS
extracts memory fragments, stores them, and returns top-k relevant fragments as a
ready-to-inject system prompt block.

```
After conversation  →  POST /sessions  →  extract → embed → store
Before LLM call     →  GET /memory     →  embed query → similarity search → return top-k + prompt_block
```

---

## Current state

**Branch:** master  
**Stage:** M5 complete  
**Stack health:** mypy 0 errors, ruff 0 issues, 5/5 smoke tests passing  
**Local config:** EXTRACTION_PROVIDER=mock, EMBEDDING_PROVIDER=local (no API keys needed)

---

## What is done

### M1 — Working vertical slice ✅
- Full pipeline end-to-end: POST /sessions → extraction → embed → store → GET /memory → re-rank → prompt_block
- Mock extractor (no API key needed for local dev)
- Local sentence-transformers embeddings (all-MiniLM-L6-v2, 384-dim)
- Docker + docker-compose stack
- 5/5 smoke tests

### M2 — Production hardening ✅ (all 8 items)
- Extraction retry with exponential backoff (3 attempts, 2s → 4s → 8s)
- Dead-letter table for exhausted jobs
- Startup env validation (fail-fast on missing keys)
- DELETE /memory/:id (scoped to calling app)
- Deduplication (cosine similarity > 0.95 = skip)
- Structured JSON logging (structlog) + X-Request-ID middleware
- Redis hot cache for GET /memory (60s TTL, SHA-256 keyed by app_id+user_id+query+params)
- Rate limiting: POST /sessions 60/min, GET /memory 120/min (slowapi, keyed by API key)
- Alembic migrations: baseline revision 17527735066b, DB stamped, future changes tracked

---

## What is next

### M3 — Developer experience ✅
- Python SDK: `sdk/python/` — sync + async `write()` / `query()` / `delete()`, zero deps beyond httpx
- TypeScript SDK: `sdk/typescript/` — typed, zero runtime deps, works in Node + edge runtimes
- CLI: `contextos keys create/list/delete`, `contextos health` — bundled with Python SDK `[cli]` extra
- Fly.io: `fly.toml` at project root, full deploy steps in README

### M4 — Multi-tenancy + management API ✅
- App management: `POST/GET/DELETE /admin/apps` — create, list, delete apps via API
- Key rotation: `POST /admin/apps/:id/keys` issues new key (raw key returned once), `DELETE` revokes
- GDPR bulk delete: `DELETE /admin/memory?user_id=X` — wipes all fragments + dead-letters, invalidates cache
- Usage: `GET /admin/apps/:id/usage` — fragment count, unique users, dead-letters, last active
- All endpoints protected by `Admin-Key` header (ADMIN_API_KEY env var); 503 if unset

### M5 — Intelligence layer ✅
- Fragment versioning: `superseded_by_id` self-FK on fragments; active fragments have NULL; migration `c4f7a2e91d05`
- Memory consolidation: cosine 0.75–0.94 = near-match → supersede old, store new with max(old, new) importance
- Decay scoring: exponential decay (30-day half-life) as 20% of composite score; replaces flat importance×similarity
- Hybrid retrieval: BM25 (Postgres tsvector ts_rank_cd) + cosine vector search, fused with RRF (k=60); only active (non-superseded) fragments returned

---

## Architecture decisions (and why)

| Decision | Choice | Reason |
|---|---|---|
| Vector store | Postgres + pgvector | Single DB handles relational + vector, no separate infra |
| Embedding provider | local (sentence-transformers) or openai | Local = no key, fast dev. OpenAI = production quality |
| Extraction provider | anthropic / openai / mock | Mock = local dev without credits |
| Retrieval | BM25 (Postgres tsvector) + cosine (pgvector), fused via RRF | Hybrid catches keyword matches cosine misses |
| Re-ranking formula | score = similarity × 0.5 + (importance/5) × 0.3 + decay × 0.2 | Balances semantic match, importance, and recency |
| Decay half-life | 30 days | Fragment relevance halves every 30 days |
| Dedup threshold | cosine > 0.95 | Catches near-exact duplicates, not paraphrases |
| Namespace | app_id + user_id | Enables cross-tool memory (global) or isolation (scope=app) |
| Auth | Bearer API key, SHA-256 hash | OpenAI-familiar pattern |
| Port mapping | 5433:5432 | Local Postgres was occupying 5432 |

---

## Key files

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI app, middleware, lifespan |
| `app/api/sessions.py` | POST /sessions — extraction pipeline, retry, dead-letter |
| `app/api/memory.py` | GET /memory, DELETE /memory/:id |
| `app/extraction/` | Extraction providers: anthropic, openai, mock |
| `app/extraction/embeddings.py` | Embedding providers: local, openai |
| `app/models/fragment.py` | ORM: App, ApiKey, Fragment, DeadLetterSession |
| `app/limiter.py` | slowapi Limiter instance (shared across routes) |
| `app/config.py` | All settings via pydantic-settings |
| `migrations/alembic/` | Alembic migration env + versions (use this going forward) |
| `migrations/001_initial.sql` | Legacy raw SQL — superseded by Alembic baseline |
| `migrations/002_dead_letter.sql` | Legacy raw SQL — superseded by Alembic baseline |
| `app/api/admin.py` | Admin API — app management, key rotation, GDPR delete, usage |
| `app/schemas/admin.py` | Pydantic schemas for admin endpoints |
| `sdk/python/` | Python SDK — `pip install ./sdk/python` or `pip install contextos` |
| `sdk/typescript/` | TypeScript SDK — copy `src/index.ts` or `npm install contextos` |
| `fly.toml` | Fly.io deploy config |
| `scripts/seed_api_key.py` | CLI to create an app + API key |
| `tests/test_smoke.py` | 5 end-to-end smoke tests |
| `docker-compose.yml` | Postgres (pgvector/pg16), Redis, app |

---

## How to run locally

```bash
# Start stack
DOCKER_HOST=unix:///Users/sverma/.docker/run/docker.sock docker compose up -d

# Seed an API key
python scripts/seed_api_key.py --app-name "test" \
  --database-url postgresql://contextos:contextos@localhost:5433/contextos

# Run smoke tests
CONTEXTOS_API_KEY=sk-... pytest tests/test_smoke.py -v

# Type check
python -m mypy app/ --ignore-missing-imports

# Lint
python -m ruff check app/
```

---

## Known gotchas

- Docker socket path: `unix:///Users/sverma/.docker/run/docker.sock` (not the default)
- Fresh DB setup: schema is in Alembic now. Run `alembic upgrade head` after `docker compose up -d` on a new machine. The raw SQL files in `migrations/` are kept for reference only.
- Alembic needs the local DB URL: `DATABASE_URL=postgresql+asyncpg://contextos:contextos@localhost:5433/contextos alembic upgrade head`
- Changing EMBEDDING_PROVIDER after data is stored requires re-embedding all fragments (384-dim local ≠ 1536-dim OpenAI)
- `add_logger_name` processor is incompatible with structlog's PrintLoggerFactory — do not add it back

---

## Open questions

1. Structured conversation format — accept `[{role, content}]` instead of raw text for better extraction quality?
2. Fragment ownership — user-scoped delete token, or app-only? (GDPR path depends on this)
3. Embedding migration strategy — how to re-embed when switching from local (384-dim) to OpenAI (1536-dim)?
