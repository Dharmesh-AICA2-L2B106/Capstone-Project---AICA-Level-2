"""workpapers file/manifest columns (prompt 3.6)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-27 22:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('workpapers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('file_ref', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('sha256', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('manifest', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('workpapers', schema=None) as batch_op:
        batch_op.drop_column('created_at')
        batch_op.drop_column('manifest')
        batch_op.drop_column('sha256')
        batch_op.drop_column('file_ref')
