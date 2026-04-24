-- ContextOS initial schema
-- Run with: psql $DATABASE_URL -f migrations/001_initial.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Apps: each third-party client that connects to ContextOS
CREATE TABLE IF NOT EXISTS apps (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- API keys: hashed, belong to an app
CREATE TABLE IF NOT EXISTS api_keys (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id      UUID NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    key_hash    TEXT NOT NULL UNIQUE,   -- SHA-256 hex of the raw key
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS api_keys_app_id_idx ON api_keys(app_id);

-- Memory fragments: the core store
CREATE TABLE IF NOT EXISTS fragments (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id         UUID NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    user_id        TEXT NOT NULL,       -- caller-supplied opaque identifier
    content        TEXT NOT NULL,
    embedding      vector(384),
    type           TEXT NOT NULL CHECK (type IN ('fact', 'preference', 'decision', 'event', 'project')),
    importance     INTEGER NOT NULL CHECK (importance BETWEEN 1 AND 5),
    source_client  TEXT,               -- e.g. "claude-terminal", "gpt-web"
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata       JSONB NOT NULL DEFAULT '{}'
);

-- Composite index for all per-user queries
CREATE INDEX IF NOT EXISTS fragments_app_user_idx ON fragments(app_id, user_id);

-- Partial index for scoped (per-app) queries
CREATE INDEX IF NOT EXISTS fragments_user_idx ON fragments(user_id);

-- ANN index for semantic retrieval (ivfflat, cosine)
-- NOTE: build after initial data load for best performance
-- lists = sqrt(expected row count); 100 is a safe default for < 1M rows
CREATE INDEX IF NOT EXISTS fragments_embedding_idx
    ON fragments USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
