"""input_vat_runs result/job/audit columns (prompt 3.12)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-27 20:10:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('input_vat_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('job_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('result', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('created_by', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('input_vat_runs', schema=None) as batch_op:
        batch_op.drop_column('created_at')
        batch_op.drop_column('created_by')
        batch_op.drop_column('result')
        batch_op.drop_column('job_id')
