"""add is_active + unique year to tournaments, seed 2026 tournament

Revision ID: a1c2026active
Revises: f4decba491d7
Create Date: 2026-05-30

This migration is additive and non-destructive:
  * adds tournaments.is_active (existing 2025 row becomes inactive/archived)
  * enforces one tournament per year (unique constraint on year)
  * inserts the 2026 tournament and marks it as the active/current one
No existing rows (users, games, predictions, the 2025 tournament) are modified
other than the 2025 tournament gaining is_active = False.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a1c2026active"
down_revision = "f4decba491d7"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add the flag. server_default=false backfills the existing 2025 row,
    #    then we drop the server default so the column matches the model
    #    (Python-side default only).
    op.add_column(
        "tournaments",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("tournaments", "is_active", server_default=None)

    # 2. One tournament per year.
    op.create_unique_constraint("uq_tournaments_year", "tournaments", ["year"])

    # 3. Seed 2026 and make it the active/current tournament.
    op.execute(
        "INSERT INTO tournaments (year, name, is_active) "
        "VALUES (2026, 'FIFA World Cup 2026', true)"
    )


def downgrade():
    op.execute("DELETE FROM tournaments WHERE year = 2026")
    op.drop_constraint("uq_tournaments_year", "tournaments", type_="unique")
    op.drop_column("tournaments", "is_active")
