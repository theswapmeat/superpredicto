"""add games.status (football-data.org match status, drives the LIVE indicator)

Revision ID: g7status
Revises: f6teamcode
Create Date: 2026-05-31

Stores the raw match status (SCHEDULED/TIMED/IN_PLAY/PAUSED/FINISHED/...) so the
UI can show a "LIVE" pulse for in-play games. Nullable; populated by the
football-data.org sync on its next run.
"""
from alembic import op
import sqlalchemy as sa


revision = "g7status"
down_revision = "f6teamcode"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("games", sa.Column("status", sa.String(), nullable=True))


def downgrade():
    op.drop_column("games", "status")
