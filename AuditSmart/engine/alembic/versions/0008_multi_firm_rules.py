"""multi-firm rule approvals: firms, clients.firm_id, firm-scoped rule versions (D42)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-01 15:10:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'firms',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('require_approved_rules', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('created_by', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.add_column(sa.Column('firm_id', sa.String(length=64), nullable=True))
        batch_op.create_foreign_key('fk_clients_firm_id', 'firms', ['firm_id'], ['id'])
        batch_op.create_index('ix_clients_firm_id', ['firm_id'], unique=False)
    with op.batch_alter_table('rule_versions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('firm_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('engagement_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('based_on_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_rule_versions_firm_id', 'firms', ['firm_id'], ['id'])
        batch_op.create_foreign_key('fk_rule_versions_engagement_id', 'engagements',
                                    ['engagement_id'], ['id'])
        batch_op.create_index('ix_rule_versions_firm_id', ['firm_id'], unique=False)
        batch_op.create_index('ix_rule_versions_engagement_id', ['engagement_id'], unique=False)
    op.create_table(
        'firm_rule_approvals',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('firm_id', sa.String(length=64), nullable=False),
        sa.Column('rule_version_id', sa.String(length=36), nullable=False),
        sa.Column('rule_key', sa.String(length=128), nullable=False),
        sa.Column('approved_by', sa.String(length=128), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['firm_id'], ['firms.id']),
        sa.ForeignKeyConstraint(['rule_version_id'], ['rule_versions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('firm_id', 'rule_version_id', name='uq_firm_rule_approval'),
    )
    op.create_index('ix_firm_rule_approvals_firm_id', 'firm_rule_approvals', ['firm_id'],
                    unique=False)


def downgrade() -> None:
    op.drop_index('ix_firm_rule_approvals_firm_id', table_name='firm_rule_approvals')
    op.drop_table('firm_rule_approvals')
    with op.batch_alter_table('rule_versions', schema=None) as batch_op:
        batch_op.drop_index('ix_rule_versions_engagement_id')
        batch_op.drop_index('ix_rule_versions_firm_id')
        batch_op.drop_constraint('fk_rule_versions_engagement_id', type_='foreignkey')
        batch_op.drop_constraint('fk_rule_versions_firm_id', type_='foreignkey')
        batch_op.drop_column('based_on_id')
        batch_op.drop_column('engagement_id')
        batch_op.drop_column('firm_id')
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.drop_index('ix_clients_firm_id')
        batch_op.drop_constraint('fk_clients_firm_id', type_='foreignkey')
        batch_op.drop_column('firm_id')
    op.drop_table('firms')
