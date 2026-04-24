"""initial_schema

Revision ID: 17527735066b
Revises:
Create Date: 2026-04-24

Baseline migration — represents the schema created by the raw SQL files
(001_initial.sql + 002_dead_letter.sql). Existing databases should be
stamped at this revision rather than run through upgrade().

  alembic stamp 17527735066b
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "17527735066b"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "apps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("app_id", UUID(as_uuid=True), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_hash", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("api_keys_app_id_idx", "api_keys", ["app_id"])

    op.create_table(
        "fragments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("app_id", UUID(as_uuid=True), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(256), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("importance", sa.Integer, nullable=False),
        sa.Column("source_client", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.CheckConstraint(
            "type IN ('fact', 'preference', 'decision', 'event', 'project')",
            name="fragment_type_check",
        ),
        sa.CheckConstraint("importance BETWEEN 1 AND 5", name="fragment_importance_check"),
    )
    op.create_index("fragments_app_user_idx", "fragments", ["app_id", "user_id"])
    op.create_index("fragments_user_idx", "fragments", ["user_id"])
    op.create_index(
        "fragments_embedding_idx",
        "fragments",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_with={"lists": "100"},
    )

    op.create_table(
        "dead_letter_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.Text, nullable=False),
        sa.Column("app_id", UUID(as_uuid=True), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(256), nullable=False),
        sa.Column("conversation", sa.Text, nullable=False),
        sa.Column("source_client", sa.String(128), nullable=True),
        sa.Column("error", sa.Text, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="1"),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("dead_letter_app_user_idx", "dead_letter_sessions", ["app_id", "user_id"])
    op.create_index("dead_letter_failed_at_idx", "dead_letter_sessions", [sa.literal_column("failed_at DESC")])


def downgrade() -> None:
    op.drop_table("dead_letter_sessions")
    op.drop_table("fragments")
    op.drop_table("api_keys")
    op.drop_table("apps")
