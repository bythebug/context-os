"""m5_fragment_versioning

Revision ID: c4f7a2e91d05
Revises: 17527735066b
Create Date: 2026-04-24

Adds fragment versioning (superseded_by_id self-FK).
When memory consolidation replaces an old fragment with a new one,
the old fragment's superseded_by_id is set to the new fragment's ID.
Active fragments have superseded_by_id = NULL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "c4f7a2e91d05"
down_revision: Union[str, Sequence[str], None] = "17527735066b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "fragments",
        sa.Column("superseded_by_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fragments_superseded_by_fk",
        "fragments",
        "fragments",
        ["superseded_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("fragments_superseded_by_idx", "fragments", ["superseded_by_id"])


def downgrade() -> None:
    op.drop_index("fragments_superseded_by_idx", "fragments")
    op.drop_constraint("fragments_superseded_by_fk", "fragments", type_="foreignkey")
    op.drop_column("fragments", "superseded_by_id")
