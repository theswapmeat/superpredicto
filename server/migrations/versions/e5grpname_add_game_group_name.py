"""add games.group_name (football-data.org group code, e.g. GROUP_A)

Revision ID: e5grpname
Revises: d4extsync
Create Date: 2026-05-31

Stores the raw group code for group-stage games so the UI can show "Group A"
instead of a generic "Group". Knockout games stay NULL. Populated by the
football-data.org sync (sync_fixtures) on the next run.
"""
from alembic import op
import sqlalchemy as sa


revision = "e5grpname"
down_revision = "d4extsync"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("games", sa.Column("group_name", sa.String(), nullable=True))


def downgrade():
    op.drop_column("games", "group_name")
