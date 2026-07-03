"""add tournaments.hide_live_predictions

Revision ID: l12hidelive
Revises: k11dropusercols
Create Date: 2026-07-03

Admin toggle backing the /predictions "hide games currently in play" switch.
When True, the predictions page shows only completed games (a game that has
kicked off but isn't finished stays hidden until it completes). Defaults to
FALSE so existing rows keep the original behaviour and the deploy is a no-op
until an admin flips the switch.
"""
from alembic import op
import sqlalchemy as sa


revision = "l12hidelive"
down_revision = "k11dropusercols"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tournaments",
        sa.Column(
            "hide_live_predictions",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("tournaments", "hide_live_predictions")
