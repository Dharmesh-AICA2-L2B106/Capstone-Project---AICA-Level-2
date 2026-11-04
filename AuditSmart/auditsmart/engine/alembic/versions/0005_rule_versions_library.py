"""rule_versions: version, domain, unit, source_ref, created_at (prompt 3.8)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28 00:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('rule_versions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.Integer(), nullable=False,
                                      server_default='1'))
        batch_op.add_column(sa.Column('domain', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('unit', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('source_ref', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('rule_versions', schema=None) as batch_op:
        batch_op.drop_column('created_at')
        batch_op.drop_column('source_ref')
        batch_op.drop_column('unit')
        batch_op.drop_column('domain')
        batch_op.drop_column('version')
