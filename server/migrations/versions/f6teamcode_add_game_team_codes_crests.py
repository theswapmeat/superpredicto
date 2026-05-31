"""add games.{home,away}_team_code + _crest (football-data.org tla + crest URLs)

Revision ID: f6teamcode
Revises: e5grpname
Create Date: 2026-05-31

Stores each team's official 3-letter code (tla, e.g. "RSA") and crest URL, so the
UI shows correct, unambiguous badges (name-slicing made both South Africa and
South Korea "SOU"). All nullable; populated by the football-data.org sync on its
next run, and NULL for unresolved knockout (TBD) slots.
"""
from alembic import op
import sqlalchemy as sa


revision = "f6teamcode"
down_revision = "e5grpname"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("games", sa.Column("home_team_code", sa.String(), nullable=True))
    op.add_column("games", sa.Column("away_team_code", sa.String(), nullable=True))
    op.add_column("games", sa.Column("home_team_crest", sa.String(), nullable=True))
    op.add_column("games", sa.Column("away_team_crest", sa.String(), nullable=True))


def downgrade():
    op.drop_column("games", "away_team_crest")
    op.drop_column("games", "home_team_crest")
    op.drop_column("games", "away_team_code")
    op.drop_column("games", "home_team_code")
