"""add users.signup_reminder_sent + pick_reminders table (reminder emails)

Revision ID: i9reminders
Revises: h8pens
Create Date: 2026-06-01

Supports two automated reminder emails:
- signup_reminder_sent: a one-shot flag so the "24h to kickoff, finish signing up"
  blast goes to each never-activated invitee exactly once.
- pick_reminders: idempotency table so the "kickoff in 2h, you haven't picked"
  nudge is sent at most once per (user, game).
"""
from alembic import op
import sqlalchemy as sa


revision = "i9reminders"
down_revision = "h8pens"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "signup_reminder_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "pick_reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "game_id", sa.Integer(), sa.ForeignKey("games.id"), nullable=False
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "game_id", name="uq_pick_reminder_user_game"),
    )


def downgrade():
    op.drop_table("pick_reminders")
    op.drop_column("users", "signup_reminder_sent")
