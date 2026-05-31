"""add games.external_id + games.manual_override (football-data.org live sync)

Revision ID: d4extsync
Revises: c3stagescoring
Create Date: 2026-05-31

- external_id: the football-data.org match id, so a Game maps 1:1 to its live
  fixture and the auto-sync can update scores without fuzzy team-name matching.
- manual_override: set True when an admin hand-edits a score, so the auto-sync
  won't overwrite their correction.
"""
from alembic import op
import sqlalchemy as sa


revision = "d4extsync"
down_revision = "c3stagescoring"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("games", sa.Column("external_id", sa.Integer(), nullable=True))
    op.add_column(
        "games",
        sa.Column(
            "manual_override", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_unique_constraint("uq_games_external_id", "games", ["external_id"])
    # Existing rows are now backfilled to False; drop the server default.
    op.alter_column("games", "manual_override", server_default=None)


def downgrade():
    op.drop_constraint("uq_games_external_id", "games", type_="unique")
    op.drop_column("games", "manual_override")
    op.drop_column("games", "external_id")
