"""drop vestigial scoring + paid/active columns from the users table

Revision ID: k11dropusercols
Revises: j10payrem
Create Date: 2026-06-04

These were the pre-migration (single-tournament) global counters/flags on users.
Scoring and payment/active status are now tracked PER TOURNAMENT on participants;
nothing in the app reads the users-table copies anymore (verified by grep across
routes, scoring, and templates — every read is on a Participant or Tournament).

Dropping them removes the only thing that made a 2025/2026 cross-tournament score
mix-up even theoretically possible: you can't accidentally read a column that no
longer exists. The stale 2025 values are discarded (they were unused).
"""
from alembic import op
import sqlalchemy as sa


revision = "k11dropusercols"
down_revision = "j10payrem"
branch_labels = None
depends_on = None

DEAD_COLUMNS = [
    "perfect_picks",
    "picks_scoring_one",
    "picks_scoring_two",
    "picks_scoring_zero",
    "invalid_picks",
    "is_paid",
    "is_active",
]


def upgrade():
    for col in DEAD_COLUMNS:
        op.drop_column("users", col)


def downgrade():
    # Recreate the columns (nullable, no data restored — they were vestigial).
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.add_column("users", sa.Column("is_paid", sa.Boolean(), nullable=True))
    op.add_column("users", sa.Column("invalid_picks", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("picks_scoring_zero", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("picks_scoring_two", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("picks_scoring_one", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("perfect_picks", sa.Integer(), nullable=True))
