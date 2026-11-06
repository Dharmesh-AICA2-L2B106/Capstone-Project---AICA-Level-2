"""watched_sources / update_alerts columns for the FTA monitor (prompt 3.9)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-28 01:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('watched_sources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('last_error', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('last_links', sa.JSON(), nullable=True))
    with op.batch_alter_table('update_alerts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kind', sa.String(length=16), nullable=False,
                                      server_default='change'))
        batch_op.add_column(sa.Column('details', sa.JSON(), nullable=True))
        batch_op.alter_column('source_id', existing_type=sa.String(length=36), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('update_alerts', schema=None) as batch_op:
        batch_op.alter_column('source_id', existing_type=sa.String(length=36), nullable=False)
        batch_op.drop_column('details')
        batch_op.drop_column('kind')
    with op.batch_alter_table('watched_sources', schema=None) as batch_op:
        batch_op.drop_column('last_links')
        batch_op.drop_column('last_error')
        batch_op.drop_column('name')
