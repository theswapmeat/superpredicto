"""add participants.payment_reminder_sent (one-shot payment-reminder flag)

Revision ID: j10payrem
Revises: i9reminders
Create Date: 2026-06-03

One-shot flag so the "you're signed up but haven't paid" email (sent ~3 days
before first kickoff) goes to each activated-but-unpaid participant exactly once.
Per-tournament, so it lives on participants, not users.
"""
from alembic import op
import sqlalchemy as sa


revision = "j10payrem"
down_revision = "i9reminders"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "participants",
        sa.Column(
            "payment_reminder_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("participants", "payment_reminder_sent")
