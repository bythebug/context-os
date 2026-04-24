# ContextOS

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Model-agnostic memory infrastructure for LLM applications.

**GitHub:** [github.com/bythebug/context-os](https://github.com/bythebug/context-os)

Any AI client — Claude, GPT, a custom agent, a terminal tool — calls two endpoints:
write after a session, query before the next one. ContextOS extracts meaningful memory
fragments, stores them, and returns the top-k most relevant as a ready-to-inject system
prompt block. The model changes. The memory doesn't.

---

## Table of Contents

1. [How it works](#how-it-works)
2. [Quickstart](#quickstart)
3. [Integration guide](#integration-guide)
4. [SDKs](#sdks)
5. [CLI](#cli)
6. [API reference](#api-reference)
7. [Admin API reference](#admin-api-reference)
8. [Deploying to Fly.io](#deploying-to-flyio)
9. [Architecture](#architecture)
10. [Configuration](#configuration)
11. [Roadmap](#roadmap)
12. [Current status](#current-status)

---

## How it works

```
After conversation  →  POST /sessions  →  extract fragments → embed → store
Before LLM call     →  GET /memory     →  embed query → similarity search → return top-k
```

A **fragment** is one discrete memory unit extracted from a conversation:

```json
{
  "id": "uuid",
  "content": "User prefers async Python over sync",
  "type": "preference",
  "importance": 3,
  "score": 0.91
}
```

`GET /memory` returns a list of fragments plus a `prompt_block` — a pre-formatted string
you paste directly into your system prompt. No processing required on the client side.

**Cross-tool memory:** `user_id` is the only key. Memory written by your Claude app is
available to your GPT app. ContextOS is the shared layer.

---

## Quickstart

### 1. Start the stack

```bash
cp .env.example .env
# Fill in your API key(s) — see Configuration section
docker compose up -d
```

### 2. Create an API key

```bash
python scripts/seed_api_key.py --app-name "my-app" \
  --database-url postgresql://contextos:contextos@localhost:5433/contextos
# → prints: API key: sk-...
```

### 3. Write a session

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Authorization: Bearer sk-..." \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "conversation": "I prefer async Python and I am deploying on Fly.io",
    "source_client": "my-app"
  }'
```

### 4. Query memory

```bash
curl "http://localhost:8000/memory?user_id=alice&q=deployment" \
  -H "Authorization: Bearer sk-..."
```

```json
{
  "user_id": "alice",
  "fragments": [
    { "content": "User decided to deploy on Fly.io", "type": "decision", "score": 0.91 }
  ],
  "prompt_block": "Relevant context about this user:\n- [decision] User decided to deploy on Fly.io (relevance: 0.91)",
  "meta": { "total_fragments": 1, "query_ms": 38 }
}
```

---

## Integration guide

ContextOS does not sit between your app and the LLM. Your app calls it at two points:
before the LLM call to fetch memory, after to save the conversation.

```
User message
    │
    ▼
GET /memory?user_id=alice&q={message}    ← fetch relevant context
    │
    ▼
Inject prompt_block into system prompt
    │
    ▼
Call Claude / GPT / any LLM             ← nothing changes here
    │
    ▼
Return response to user
    │
    ▼
POST /sessions                           ← save conversation
```

### Raw HTTP — Python

```python
import httpx
import anthropic

CTX_URL = "http://localhost:8000"
CTX_KEY = "sk-your-contextos-key"

async def chat(user_id: str, message: str) -> str:
    # 1. Fetch memory
    memory = httpx.get(
        f"{CTX_URL}/memory",
        params={"user_id": user_id, "q": message},
        headers={"Authorization": f"Bearer {CTX_KEY}"},
    ).json()

    # 2. Build system prompt
    system = "You are a helpful assistant."
    if memory["prompt_block"]:
        system += f"\n\n{memory['prompt_block']}"

    # 3. Call LLM as normal
    response = anthropic.Anthropic().messages.create(
        model="claude-opus-4-6",
        system=system,
        messages=[{"role": "user", "content": message}],
    )
    reply = response.content[0].text

    # 4. Save to memory
    httpx.post(
        f"{CTX_URL}/sessions",
        json={"user_id": user_id, "conversation": f"User: {message}\nAssistant: {reply}"},
        headers={"Authorization": f"Bearer {CTX_KEY}"},
    )
    return reply
```

### Raw HTTP — TypeScript

```typescript
const CTX_URL = "http://localhost:8000";
const CTX_KEY = "sk-your-contextos-key";
const ctxHeaders = { Authorization: `Bearer ${CTX_KEY}` };

async function chat(userId: string, message: string): Promise<string> {
  // 1. Fetch memory
  const mem = await fetch(
    `${CTX_URL}/memory?user_id=${userId}&q=${encodeURIComponent(message)}`,
    { headers: ctxHeaders }
  ).then(r => r.json());

  // 2. Build system prompt
  const system = mem.prompt_block
    ? `You are a helpful assistant.\n\n${mem.prompt_block}`
    : "You are a helpful assistant.";

  // 3. Call LLM
  const reply = await callYourLLM(system, message);

  // 4. Save to memory
  await fetch(`${CTX_URL}/sessions`, {
    method: "POST",
    headers: { ...ctxHeaders, "content-type": "application/json" },
    body: JSON.stringify({ user_id: userId, conversation: `User: ${message}\nAssistant: ${reply}` }),
  });

  return reply;
}
```

---

## SDKs

### Python SDK

```bash
pip install ./sdk/python          # local install
# pip install contextos           # once published to PyPI
```

```python
from contextos import ContextOS

client = ContextOS(api_key="sk-...", base_url="https://your-app.fly.dev")

# After a conversation
client.write(
    user_id="alice",
    conversation="User: I use async Python\nAssistant: Noted.",
    source_client="my-app",          # optional
)

# Before an LLM call
memory = client.query(user_id="alice", q=user_message)
system = f"You are a helpful assistant.\n\n{memory.prompt_block}"

# Delete a specific fragment
client.delete(fragment_id="uuid-...")
```

**Async versions:** `client.awrite()`, `client.aquery()`, `client.adelete()`

**`query()` options:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `top_k` | int | 10 | Max fragments to return |
| `scope` | `"global"` \| `"app"` | `"global"` | Cross-app or this app only |
| `type` | str | — | Filter by fragment type |

### TypeScript SDK

```bash
# npm install contextos           # once published to npm
# Until then: copy sdk/typescript/src/index.ts into your project
```

```typescript
import { ContextOS } from "contextos";

const client = new ContextOS({
  apiKey: "sk-...",
  baseUrl: "https://your-app.fly.dev",
});

// After a conversation
await client.write("alice", `User: ${message}\nAssistant: ${reply}`, {
  source_client: "my-app",
});

// Before an LLM call
const memory = await client.query("alice", userMessage);
const system = `You are helpful.\n\n${memory.prompt_block}`;

// Delete a fragment
await client.delete("uuid-...");
```

Zero runtime dependencies. Works in Node.js and edge runtimes (Cloudflare Workers, Vercel).

---

## CLI

Bundled with the Python SDK under the `[cli]` extra.

```bash
pip install "./sdk/python[cli]"
```

**Key management:**

```bash
# Create a new app and API key
contextos keys create --app-name my-app \
  --database-url postgresql://contextos:contextos@localhost:5433/contextos

# List all apps and key counts
contextos keys list --database-url postgresql://...

# Revoke a key by ID
contextos keys delete <key-id> --database-url postgresql://...
```

**Health check:**

```bash
contextos health --url https://your-app.fly.dev
# Status:   ok
# Postgres: ok
# Redis:    ok
```

The `DATABASE_URL` env var is read automatically if set, so `--database-url` can be omitted.

---

## API reference

All endpoints require `Authorization: Bearer <api-key>`.

**Rate limits:** `POST /sessions` — 60 requests/minute. `GET /memory` — 120 requests/minute.
Limits are keyed by API key. Exceeding them returns `429 Too Many Requests`.

---

### `POST /sessions`

Ingest a conversation. Extraction runs asynchronously in the background.

**Request body:**
```json
{
  "user_id": "string (required)",
  "conversation": "string (required) — raw conversation text",
  "source_client": "string (optional) — e.g. 'claude-terminal'",
  "metadata": "object (optional) — arbitrary key/value, stored with each fragment"
}
```

**Response `202 Accepted`:**
```json
{
  "session_id": "uuid",
  "user_id": "string",
  "status": "accepted",
  "message": "Conversation received. Memory extraction is running in the background."
}
```

---

### `GET /memory`

Retrieve relevant memory fragments for a user. Responses are cached in Redis for 60 seconds.

**Query parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `user_id` | string | yes | — | User to retrieve memory for |
| `q` | string | yes | — | Semantic search query |
| `top_k` | int | no | 10 | Max fragments returned (1–50) |
| `scope` | `global`\|`app` | no | `global` | `global` = all apps; `app` = this app only |
| `type` | string | no | — | Filter by type: `fact`, `preference`, `decision`, `event`, `project` |

**Response `200 OK`:**
```json
{
  "user_id": "string",
  "fragments": [
    {
      "id": "uuid",
      "content": "string",
      "type": "fact|preference|decision|event|project",
      "importance": 1-5,
      "source_client": "string|null",
      "score": 0.0-1.0,
      "created_at": "ISO timestamp"
    }
  ],
  "prompt_block": "Relevant context about this user:\n- [type] content (relevance: score)\n...",
  "meta": { "total_fragments": int, "query_ms": int }
}
```

---

### `DELETE /memory/:id`

Delete a fragment by ID. Scoped to the calling app — you can only delete fragments your app created.

**Response:** `204 No Content` or `404 Not Found`

---

### `GET /health`

```json
{ "status": "ok", "postgres": "ok", "redis": "ok" }
```

Returns `"degraded"` if either dependency is unreachable.

---

### Request tracing

Every response includes an `X-Request-ID` header. Pass your own to propagate a trace ID:

```
X-Request-ID: my-trace-id-123
```

If omitted, ContextOS generates a UUID. The same ID is bound to all structured log lines
for that request, making it trivial to trace a session write through extraction, embedding,
and storage in the logs.

---

## Admin API reference

All admin endpoints require `Admin-Key: <value>` header where `<value>` matches the
`ADMIN_API_KEY` environment variable. If `ADMIN_API_KEY` is unset, all `/admin` endpoints
return `503 Service Unavailable`.

| Endpoint | Method | Description |
|---|---|---|
| `/admin/apps` | `POST` | Create an app — `{"name": "..."}` |
| `/admin/apps` | `GET` | List all apps |
| `/admin/apps/:id` | `GET` | Get a single app |
| `/admin/apps/:id` | `DELETE` | Delete app and all its data (cascades to keys, fragments, dead-letters) |
| `/admin/apps/:id/keys` | `GET` | List API keys for an app |
| `/admin/apps/:id/keys` | `POST` | Issue a new API key — raw key returned once, store it immediately |
| `/admin/apps/:id/keys/:key_id` | `DELETE` | Revoke a specific API key |
| `/admin/apps/:id/usage` | `GET` | Fragment count, unique users, dead-letter count, last active time |
| `/admin/memory` | `DELETE` | GDPR bulk delete — wipe all fragments for a user |

**`DELETE /admin/memory` parameters:**

| Parameter | Required | Description |
|---|---|---|
| `user_id` | yes | Wipe all fragments for this user |
| `app_id` | no | Scope deletion to one app only |

**Example — create app and issue key:**

```bash
# Create an app
curl -X POST http://localhost:8000/admin/apps \
  -H "Admin-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-app"}'
# → {"id": "uuid", "name": "my-app", "created_at": "..."}

# Issue a key for that app
curl -X POST http://localhost:8000/admin/apps/<app-id>/keys \
  -H "Admin-Key: your-admin-key"
# → {"id": "uuid", "app_id": "...", "key": "sk-...", "created_at": "..."}
#   ^ raw key returned here and never again
```

**Example — usage stats:**

```bash
curl http://localhost:8000/admin/apps/<app-id>/usage \
  -H "Admin-Key: your-admin-key"
```

```json
{
  "app_id": "uuid",
  "app_name": "my-app",
  "total_fragments": 142,
  "unique_users": 8,
  "total_dead_letters": 0,
  "last_active": "2026-04-24T17:42:00Z"
}
```

**Example — GDPR bulk delete:**

```bash
# Delete all memory for a user across all apps
curl -X DELETE "http://localhost:8000/admin/memory?user_id=alice" \
  -H "Admin-Key: your-admin-key"
# → {"user_id": "alice", "deleted_fragments": 37, "deleted_dead_letters": 0}

# Scope to a single app
curl -X DELETE "http://localhost:8000/admin/memory?user_id=alice&app_id=<app-id>" \
  -H "Admin-Key: your-admin-key"
```

---

## Deploying to Fly.io

```bash
# 1. Install flyctl
brew install flyctl && fly auth login

# 2. Create the app (update app name in fly.toml first)
fly apps create contextos

# 3. Provision Postgres with pgvector
fly postgres create --name contextos-db
fly postgres attach contextos-db

# 4. Provision Redis
fly redis create --name contextos-redis
fly secrets set REDIS_URL=redis://...   # copy URL from previous command output

# 5. Set secrets
fly secrets set ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY + EXTRACTION_PROVIDER=openai
fly secrets set ADMIN_API_KEY=$(openssl rand -hex 32)

# 6. Deploy
fly deploy

# 7. Run migrations
fly ssh console -C "DATABASE_URL=\$DATABASE_URL alembic upgrade head"

# 8. Create your first API key
fly ssh console -C "python scripts/seed_api_key.py --app-name prod --database-url \$DATABASE_URL"
```

**Embedding note:** The default `fly.toml` uses `EMBEDDING_PROVIDER=local` (sentence-transformers,
no API key needed). The model is pre-warmed at startup. If you switch to
`EMBEDDING_PROVIDER=openai`, set `OPENAI_API_KEY` and `EMBEDDING_DIMENSIONS=1536`.

---

## Architecture

### Stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python + FastAPI | Native to the LLM ecosystem |
| Vector store | Postgres + pgvector | Single DB handles relational + vector, no separate infra |
| Hot cache | Redis | 60s TTL on GET /memory — skips embedding + DB on repeat queries |
| Auth | Bearer API key, SHA-256 hash | OpenAI-familiar pattern every LLM dev already knows |
| Migrations | Alembic | Versioned schema changes, autogenerate support |

### Data model

```
apps                 — each third-party client that connects to ContextOS
api_keys             — SHA-256 hashed keys, belong to an app
fragments            — memory units: content + embedding + type + importance + metadata
dead_letter_sessions — failed extraction jobs after all retries exhausted
```

**Fragment types:** `fact` · `preference` · `decision` · `event` · `project`

**Namespace:** `app_id + user_id` composite. Default queries return all fragments for a
user across all apps (cross-tool memory). Pass `?scope=app` for isolation.

### Extraction pipeline

```
POST /sessions received
        │
        ▼ (background task — returns 202 immediately)
LLM extraction call (Anthropic / OpenAI / mock)
  → returns [{ content, type, importance }]
        │
        ▼
Embed each fragment (sentence-transformers local / OpenAI)
        │
        ▼
For each fragment, find closest active fragment in DB:
  similarity ≥ 0.95  → exact duplicate, skip
  similarity 0.75–0.94 → near-match: supersede old fragment, store new with max importance
  similarity < 0.75  → new information, store fresh
        │
        ▼
Store in Postgres/pgvector
        │
  on failure → retry up to 3× with exponential backoff (2s, 4s, 8s)
             → dead-letter table after exhaustion
```

### Retrieval pipeline

```
GET /memory received
        │
        ▼
Check Redis cache (60s TTL, keyed by user_id + query hash + params)
  → cache hit: return immediately
        │
        ▼ (cache miss)
Embed query string
        │
        ▼ (two searches in parallel, active fragments only)
Vector search: pgvector cosine distance  ──┐
BM25 text search: Postgres ts_rank_cd    ──┤
                                           ▼
                             Reciprocal Rank Fusion (k=60)
                             → merged candidate set
        │
        ▼
Re-rank: score = similarity × 0.5 + (importance/5) × 0.3 + decay × 0.2
  decay = exp(-ln2 × age_days / 30)  — halves every 30 days
        │
        ▼
Write result to Redis cache
        │
        ▼
Format prompt_block + return fragments
```

---

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Default | Description |
|---|---|---|
| `EXTRACTION_PROVIDER` | `anthropic` | `anthropic` · `openai` · `mock` (no API key, for local dev) |
| `ANTHROPIC_API_KEY` | — | Required when `EXTRACTION_PROVIDER=anthropic` |
| `OPENAI_API_KEY` | — | Required when `EXTRACTION_PROVIDER=openai` or `EMBEDDING_PROVIDER=openai` |
| `EMBEDDING_PROVIDER` | `local` | `local` (sentence-transformers, 384-dim) · `openai` (1536-dim) |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model name |
| `EMBEDDING_DIMENSIONS` | `384` | Must match model output (384 for local, 1536 for OpenAI) |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Postgres connection string (asyncpg driver) |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string |
| `ADMIN_API_KEY` | — | Required to enable `/admin` endpoints. Generates a warning at startup if unset. |

> **Startup validation:** The app fails fast if required keys are missing.
> `EXTRACTION_PROVIDER=anthropic` without `ANTHROPIC_API_KEY` → immediate exit with a clear error.
> Use `EXTRACTION_PROVIDER=mock` for local development without API keys.

> **Embedding migration:** Changing `EMBEDDING_PROVIDER` after data is stored requires
> re-embedding all fragments (384-dim ≠ 1536-dim). Plan this before going to production.

---

## Roadmap

### M1 — Working vertical slice ✅
Full pipeline end-to-end. 5/5 smoke tests passing.

### M2 — Production hardening ✅
- [x] Extraction retry + exponential backoff + dead-letter table
- [x] Startup env validation (fail-fast on missing keys)
- [x] `DELETE /memory/:id` (scoped to calling app)
- [x] Deduplication (cosine > 0.95 = skip)
- [x] Structured JSON logging (structlog) + `X-Request-ID` tracing
- [x] Redis hot cache for `GET /memory` (60s TTL)
- [x] Rate limiting per API key (slowapi)
- [x] Alembic migrations

### M3 — Developer experience ✅
- [x] Python SDK — sync + async `write()` / `query()` / `delete()`
- [x] TypeScript SDK — typed, zero runtime dependencies
- [x] CLI — `contextos keys create/list/delete`, `contextos health`
- [x] Fly.io deploy — `fly.toml` + step-by-step guide

### M4 — Multi-tenancy + management API ✅
- [x] App management endpoints (`POST/GET/DELETE /admin/apps`)
- [x] Key rotation (`POST/DELETE /admin/apps/:id/keys`)
- [x] GDPR bulk delete (`DELETE /admin/memory?user_id=...`)
- [x] Usage tracking per app (`GET /admin/apps/:id/usage`)

### M5 — Intelligence layer ✅
- [x] Fragment versioning — `superseded_by_id` tracks which fragment replaced which; only active fragments are queried
- [x] Memory consolidation — near-matches (cosine 0.75–0.94) automatically supersede old fragments, preserving the highest importance level
- [x] Decay scoring — exponential time decay (30-day half-life) reduces weight of stale fragments
- [x] Hybrid retrieval — BM25 (Postgres full-text) + cosine (pgvector) fused with Reciprocal Rank Fusion

---

## Current status

**Branch:** `master` · **Stage:** M5 complete · **Health:** mypy 0 errors · ruff 0 issues · 5/5 smoke tests passing

Running locally with `EXTRACTION_PROVIDER=mock` and `EMBEDDING_PROVIDER=local` —
no API keys required for development.
