# ContextOS — Master Context

Authoritative context for any agent or human continuing work on this project.
Read this before anything else. Update it after completing any meaningful work.

---

## The goal

**Cross-app personal memory OS. Your AI tools have different brains. ContextOS gives them one.**

Claude remembers Claude. ChatGPT remembers ChatGPT. Your custom agent remembers nothing.
ContextOS is the shared memory layer that runs on your machine — any LLM reads from it,
any LLM writes to it. `user_id` is the only key. Memory written by your Claude app is
instantly available to your GPT app. Your data. No vendor lock-in.

```python
# Claude app writes Alice's memory after a conversation
client.post("/sessions", json={"user_id": "alice", "conversation": "..."})

# GPT app reads what the Claude app learned — same server, same user_id
mem = client.get("/memory", params={"user_id": "alice", "q": "alice's preferences"})
# → Alice never re-introduced herself. Your GPT app already knows her.
```

**This is the demo. Two apps. One brain. Run it in a YC interview.**

---

## Why this framing (don't drift from it)

- **mem0** = per-app CLOUD memory, $24M YC-backed, 41k stars, 80k devs, dominant. Memory written by one app does NOT travel to another. We are not competing here.
- **ChatGPT Memory** = siloed to ChatGPT, on OpenAI's servers.
- **Claude Memory** = siloed to Claude.ai, on Anthropic's servers.
- **MCP memory servers** = primitive, single-LLM, no extraction, no hybrid retrieval.
- **Cross-app personal memory running locally** = completely unoccupied. No funded company has claimed it.

Pitch: *"You use Claude and ChatGPT. Do they know each other? ContextOS fixes that."*

---

## Current state

| Item | Status |
|---|---|
| Branch | master / main |
| Stage | M5 complete · M6 in progress |
| API health | mypy 0 errors · ruff 0 issues · 5/5 smoke tests passing |
| Local config | EXTRACTION_PROVIDER=mock · EMBEDDING_PROVIDER=local (no API keys needed) |
| Landing page | Updated to cross-app framing ✅ |
| README | Updated to cross-app framing ✅ |
| PyPI | Not published — still local install only |
| `contextos start` CLI | Does NOT exist yet — only `contextos keys` + `contextos health` |

---

## What's done (M1–M5 complete)

### M1 — Working vertical slice ✅
- Full pipeline: POST /sessions → extract → embed → store → GET /memory → re-rank → prompt_block
- Mock extractor (no API key for local dev), local sentence-transformers (all-MiniLM-L6-v2, 384-dim)
- Docker + docker-compose, 5/5 smoke tests

### M2 — Production hardening ✅
- Extraction retry with exponential backoff (3×: 2s / 4s / 8s) + dead-letter table
- Startup env validation (fail-fast on missing keys)
- DELETE /memory/:id scoped to calling app
- Deduplication: cosine > 0.95 = skip
- Structured JSON logging (structlog) + X-Request-ID middleware
- Redis hot cache for GET /memory (60s TTL, SHA-256 keyed by app+user+query+params)
- Rate limiting: 60 req/min writes, 120 req/min reads (slowapi, keyed by API key)
- Alembic migrations: baseline revision 17527735066b

### M3 — Developer experience ✅
- Python SDK: `sdk/python/` — sync + async `write()` / `query()` / `delete()`, httpx only
- TypeScript SDK: `sdk/typescript/` — typed, zero runtime deps, Node + edge runtimes
- CLI: `contextos keys create/list/delete`, `contextos health`
- Fly.io: `fly.toml` + full deploy guide in README

### M4 — Multi-tenancy + admin API ✅
- App management: `POST/GET/DELETE /admin/apps`
- Key rotation: `POST/DELETE /admin/apps/:id/keys` (raw key returned once)
- GDPR bulk delete: `DELETE /admin/memory?user_id=X`
- Usage stats: `GET /admin/apps/:id/usage`
- All admin endpoints protected by `Admin-Key` header

### M5 — Intelligence layer ✅
- Fragment versioning: `superseded_by_id` self-FK; only NULL (active) fragments are queried
- Memory consolidation: cosine 0.75–0.94 = near-match → supersede old, store new with max importance
- Decay scoring: exponential decay, 30-day half-life, 20% weight in composite score
- Hybrid retrieval: BM25 (Postgres tsvector) + cosine (pgvector), fused with RRF (k=60)
- Re-rank formula: `score = similarity × 0.5 + (importance/5) × 0.3 + decay × 0.2`

---

## What's next (M6 — cross-app distribution)

**Priority order:**

1. **45-second screencast demo** — two LLM apps (Claude + GPT) sharing memory through ContextOS. This is the pitch. Record it before anything else.
2. **`contextos start` CLI** — thin wrapper around `docker compose up -d`. Zero magic. Just makes the onboarding story work.
3. **`pip install contextos`** — publish Python SDK to PyPI. Polish API, clean errors, README with 5-line example.
4. **Docker Hub** — `docker pull bythebug/contextos`. GitHub Actions build + push on every release tag.
5. **Talk to 5 developers** — show screencast, ask "Is this a problem you have?" Find them on HN, Twitter/X, LlamaIndex / LangChain Discord.
6. **TypeScript npm** — deferred until 3 pilot integrations confirm demand.

**Pivot trigger:** If fewer than 3 of 5 conversations show genuine interest (not polite interest), revisit framing.

**Success criteria (Week 3):** Screencast posted. At least 50 organic shares/comments expressing "I want this."

---

## Code vs. pitch gaps (fix in M6)

| Item | Pitch says | Code today |
|---|---|---|
| Server start | `contextos start` (CLI) | Manual `docker compose up -d` |
| Python install | `pip install contextos` (PyPI) | `pip install ./sdk/python` (local) |
| SDK class name | `Client` (design doc example) | `ContextOS` class |
| TypeScript | `npm install contextos` | Local copy only |

---

## Architecture decisions

| Decision | Choice | Reason |
|---|---|---|
| Vector store | Postgres + pgvector | Single DB for relational + vector, no separate infra |
| Embedding | local (sentence-transformers) or openai | Local = no key for dev. OpenAI = production quality |
| Extraction | anthropic / openai / mock | Mock = local dev without API credits |
| Retrieval | BM25 + cosine via RRF | Hybrid catches what pure vector misses |
| Dedup threshold | cosine > 0.95 | Near-exact duplicates only, not paraphrases |
| Namespace | app_id + user_id | Cross-tool memory (global) or per-app isolation (scope=app) |
| Auth | Bearer API key, SHA-256 hash | OpenAI-familiar pattern, raw key shown once |
| Port mapping | 5433:5432 | Local Postgres occupies 5432 |

---

## Key files

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI app, middleware, lifespan (startup validation + model warm) |
| `app/api/sessions.py` | POST /sessions — extraction pipeline, retry, dead-letter |
| `app/api/memory.py` | GET /memory, DELETE /memory/:id |
| `app/api/admin.py` | Admin API — app management, key rotation, GDPR delete, usage |
| `app/extraction/` | Extraction providers: anthropic, openai, mock |
| `app/extraction/embeddings.py` | Embedding providers: local, openai |
| `app/models/fragment.py` | ORM: App, ApiKey, Fragment, DeadLetterSession |
| `app/config.py` | All settings via pydantic-settings |
| `migrations/alembic/` | Alembic env + versions — use this, not the raw SQL files |
| `sdk/python/` | Python SDK |
| `sdk/typescript/` | TypeScript SDK |
| `scripts/seed_api_key.py` | Create an app + API key |
| `tests/test_smoke.py` | 5 end-to-end smoke tests |
| `docker-compose.yml` | Postgres (pgvector/pg16), Redis, app |
| `fly.toml` | Fly.io deploy config |
| `docs/index.html` | Landing page — dark theme, cross-app framing |
| `PROGRESS.md` | Running log of completed work |

---

## How to run locally

```bash
# Start stack
DOCKER_HOST=unix:///Users/sverma/.docker/run/docker.sock docker compose up -d

# Create an API key
python scripts/seed_api_key.py --app-name "test" \
  --database-url postgresql://contextos:contextos@localhost:5433/contextos

# Smoke tests
CONTEXTOS_API_KEY=sk-... pytest tests/test_smoke.py -v

# Type check + lint
python -m mypy app/ --ignore-missing-imports
python -m ruff check app/
```

---

## Known gotchas

- **Docker socket:** `unix:///Users/sverma/.docker/run/docker.sock` (not the default path)
- **Fresh DB:** Schema lives in Alembic now. Run `DATABASE_URL=postgresql+asyncpg://contextos:contextos@localhost:5433/contextos alembic upgrade head` on a new machine. The raw SQL files in `migrations/` are kept for reference only.
- **Embedding migration:** Changing `EMBEDDING_PROVIDER` after data is stored requires re-embedding all fragments (384-dim ≠ 1536-dim). Plan before going to production.
- **air-gapped / offline:** sentence-transformers downloads the model from HuggingFace on first use. For offline deployment, switch to `EMBEDDING_PROVIDER=openai` or pre-pull the model into the Docker image.
- **structlog:** `add_logger_name` processor is incompatible with `PrintLoggerFactory` — do not add it back.

---

## Design doc (approved 2026-04-24)

`~/.gstack/projects/context-os/sverma-main-design-20260424-144613.md`

Status: APPROVED · Adversarial review score: 8.5/10

---

## Progress log

Update this section at the end of every session. Newest entries at top.

### 2026-04-24
- [x] Ran /office-hours — concluded cross-app personal memory is the unoccupied position
- [x] New pitch agreed: "Your AI tools have different brains. ContextOS gives them one."
- [x] Confirmed we are NOT competing with mem0 — different market entirely
- [x] Chose SDK + Server Hybrid: `pip install contextos` + `contextos start` CLI
- [x] Design doc approved 8.5/10 adversarial review
- [x] `docs/index.html` — hero, how-it-works, features, quickstart all rewritten with cross-app framing
- [x] Added "Two apps, one brain" demo tab to quickstart (shows the canonical cross-app code)
- [x] `README.md` — new opening paragraph + cross-app code example + M6 roadmap section
- [x] `MEMORY.md` — rebuilt as single source of truth (this file)
- [x] `CLAUDE.md` — updated stage (was "M2", now "M5 complete / M6 in progress"), correct framing
- [x] `.gitignore` — removed MEMORY.md and CLAUDE.md so they push to GitHub
- [x] GitHub Pages `.nojekyll` fix — site was rendering as unstyled text (Jekyll was overriding CSS)
- [x] Pushed all changes to GitHub main

### Before 2026-04-24 (M1–M5)
- [x] M1: Working vertical slice — full pipeline, 5/5 smoke tests
- [x] M2: Production hardening — retry, dead-letter, rate limiting, Redis cache, structlog
- [x] M3: Developer experience — Python SDK, TypeScript SDK, CLI, Fly.io deploy
- [x] M4: Multi-tenancy — admin API, key rotation, GDPR bulk delete, usage stats
- [x] M5: Intelligence layer — fragment versioning, consolidation, decay scoring, hybrid retrieval (BM25 + pgvector + RRF)
