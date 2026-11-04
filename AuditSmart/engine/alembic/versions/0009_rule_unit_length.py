"""rule_versions.unit: VARCHAR(32) -> VARCHAR(128) (D49)

Three seed rules (je.vague_narration.keywords, je.sensitive_account_types,
je.sensitive_account_codes) carry a unit longer than 32 characters. SQLite does not enforce
VARCHAR lengths, so this only showed on PostgreSQL (first Render deploy rehearsal).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-02 17:10:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('rule_versions', schema=None) as batch_op:
        batch_op.alter_column('unit', existing_type=sa.String(length=32),
                              type_=sa.String(length=128), existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('rule_versions', schema=None) as batch_op:
        batch_op.alter_column('unit', existing_type=sa.String(length=128),
                              type_=sa.String(length=32), existing_nullable=True)
