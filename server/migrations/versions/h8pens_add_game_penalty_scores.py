"""add games.{home,away}_team_pens (cosmetic penalty-shootout result)

Revision ID: h8pens
Revises: g7status
Create Date: 2026-05-31

Stores the penalty-shootout score for knockout games decided on penalties. Purely
cosmetic — never used in scoring (picks are matched on the post-extra-time score,
penalties excluded). Surfaced in the UI via Game.pens_label. Nullable; populated
by the football-data.org sync.
"""
from alembic import op
import sqlalchemy as sa


revision = "h8pens"
down_revision = "g7status"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("games", sa.Column("home_team_pens", sa.Integer(), nullable=True))
    op.add_column("games", sa.Column("away_team_pens", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("games", "away_team_pens")
    op.drop_column("games", "home_team_pens")
