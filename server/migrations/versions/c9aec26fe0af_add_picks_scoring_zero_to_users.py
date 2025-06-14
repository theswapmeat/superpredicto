"""Add picks_scoring_zero to users

Revision ID: c9aec26fe0af
Revises: d97f29c87dd2
Create Date: 2025-06-06 16:37:08.421066

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9aec26fe0af'
down_revision = 'd97f29c87dd2'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('picks_scoring_zero', sa.Integer(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('picks_scoring_zero')

    # ### end Alembic commands ###
