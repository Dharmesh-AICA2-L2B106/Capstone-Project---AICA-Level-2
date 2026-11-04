"""je_runs result/job/audit columns; emirate_profiles.half_days (prompt 3.4)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27 19:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('je_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('job_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('result', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('created_by', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table('emirate_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('half_days', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('emirate_profiles', schema=None) as batch_op:
        batch_op.drop_column('half_days')
    with op.batch_alter_table('je_runs', schema=None) as batch_op:
        batch_op.drop_column('created_at')
        batch_op.drop_column('created_by')
        batch_op.drop_column('result')
        batch_op.drop_column('job_id')
