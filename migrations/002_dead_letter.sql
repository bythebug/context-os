-- Dead-letter table for failed extraction jobs
-- Rows here mean extraction was attempted and exhausted all retries.

CREATE TABLE IF NOT EXISTS dead_letter_sessions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    TEXT NOT NULL,
    app_id        UUID NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    user_id       TEXT NOT NULL,
    conversation  TEXT NOT NULL,
    source_client TEXT,
    error         TEXT NOT NULL,
    attempts      INTEGER NOT NULL DEFAULT 1,
    failed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata      JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS dead_letter_app_user_idx ON dead_letter_sessions(app_id, user_id);
CREATE INDEX IF NOT EXISTS dead_letter_failed_at_idx ON dead_letter_sessions(failed_at DESC);
