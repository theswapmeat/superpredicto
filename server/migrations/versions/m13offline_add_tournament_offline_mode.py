"""add tournaments.offline_mode

Revision ID: m13offline
Revises: l12hidelive
Create Date: 2026-07-10

Admin "Offline / manual mode" switch, for when the live-scores API subscription
lapses. When True the app pauses the score sync, freezes the leaderboard (no
live polling, completed games only), and hides provisional scoring on the
predictions page. Defaults to FALSE so existing rows keep normal live behaviour
and the deploy is a no-op until an admin flips the switch.
"""
from alembic import op
import sqlalchemy as sa


revision = "m13offline"
down_revision = "l12hidelive"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tournaments",
        sa.Column(
            "offline_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("tournaments", "offline_mode")
