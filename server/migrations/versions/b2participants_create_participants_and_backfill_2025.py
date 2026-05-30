"""create participants table and backfill 2025 players

Revision ID: b2participants
Revises: a1c2026active
Create Date: 2026-05-30

Adds the per-tournament membership table and enrolls the existing 12 completed
2025 players as participants of the 2025 tournament (preserving their paid/active
status). Excludes the admin account and any incomplete invite (no password / no
display name). The 2026 tournament starts with NO participants — the admin adds
them via the dashboard.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b2participants"
down_revision = "a1c2026active"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "participants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tournament_id", sa.Integer(), nullable=False),
        sa.Column("is_paid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_participants_user_id"
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"], ["tournaments.id"], name="fk_participants_tournament_id"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_participants"),
        sa.UniqueConstraint(
            "user_id", "tournament_id", name="uq_participant_user_tournament"
        ),
    )

    # Backfill the 12 completed 2025 players into the 2025 tournament.
    op.execute(
        """
        INSERT INTO participants (user_id, tournament_id, is_paid, is_active, joined_at)
        SELECT u.id,
               (SELECT id FROM tournaments WHERE year = 2025),
               COALESCE(u.is_paid, false),
               COALESCE(u.is_active, true),
               COALESCE(u.created_at, now())
        FROM users u
        WHERE u.email <> 'admin@superpredicto.com'
          AND u.password_hash IS NOT NULL
          AND u.display_name IS NOT NULL
          AND u.display_name <> ''
        """
    )


def downgrade():
    op.drop_table("participants")
