"""add games.stage and per-tournament scoring columns on participants

Revision ID: c3stagescoring
Revises: b2participants
Create Date: 2026-05-30

* games.stage ("group"/"knockout") — replaces the game_number >= 49 hardcode.
  Backfills the 2025 games: game_number >= 49 -> knockout, else group.
* participants gains the five scoring counters (perfect_picks, picks_scoring_one,
  picks_scoring_two, picks_scoring_zero, invalid_picks) so scores are tracked per
  tournament instead of globally on the user row.
"""
from alembic import op
import sqlalchemy as sa

revision = "c3stagescoring"
down_revision = "b2participants"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("games", sa.Column("stage", sa.String(), nullable=True))
    # Backfill 2025 stage from the old knockout convention (games 49-63 were knockout).
    op.execute(
        """
        UPDATE games
        SET stage = CASE WHEN game_number >= 49 THEN 'knockout' ELSE 'group' END
        WHERE tournament_id = (SELECT id FROM tournaments WHERE year = 2025)
        """
    )

    for col in (
        "perfect_picks",
        "picks_scoring_one",
        "picks_scoring_two",
        "picks_scoring_zero",
        "invalid_picks",
    ):
        op.add_column(
            "participants",
            sa.Column(col, sa.Integer(), nullable=True, server_default="0"),
        )
    # Drop the server defaults so the columns match the model (Python-side default).
    for col in (
        "perfect_picks",
        "picks_scoring_one",
        "picks_scoring_two",
        "picks_scoring_zero",
        "invalid_picks",
    ):
        op.alter_column("participants", col, server_default=None)


def downgrade():
    for col in (
        "perfect_picks",
        "picks_scoring_one",
        "picks_scoring_two",
        "picks_scoring_zero",
        "invalid_picks",
    ):
        op.drop_column("participants", col)
    op.drop_column("games", "stage")
