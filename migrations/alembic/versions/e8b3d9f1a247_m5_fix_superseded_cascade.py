"""m5_fix_superseded_cascade

Revision ID: e8b3d9f1a247
Revises: c4f7a2e91d05
Create Date: 2026-04-24

Change fragments.superseded_by_id FK from ON DELETE SET NULL to ON DELETE CASCADE.

SET NULL caused a resurrection bug: deleting an active fragment (B) would set
B's predecessors' superseded_by_id to NULL, making old superseded fragments
visible in queries again. CASCADE deletes the superseded chain when the active
replacement is deleted, which is the correct semantic for memory deletion.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "e8b3d9f1a247"
down_revision: Union[str, Sequence[str], None] = "c4f7a2e91d05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("fragments_superseded_by_fk", "fragments", type_="foreignkey")
    op.create_foreign_key(
        "fragments_superseded_by_fk",
        "fragments",
        "fragments",
        ["superseded_by_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fragments_superseded_by_fk", "fragments", type_="foreignkey")
    op.create_foreign_key(
        "fragments_superseded_by_fk",
        "fragments",
        "fragments",
        ["superseded_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
