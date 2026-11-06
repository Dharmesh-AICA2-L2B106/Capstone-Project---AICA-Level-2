"""clients.client_code: unique per firm instead of globally (D52)

The front end of each firm chooses its own client codes, so two firms may both use "C001".
Replaces the unnamed global UNIQUE(client_code) from 0001 with
UNIQUE(firm_id, client_code) named uq_clients_firm_code.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-02 18:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None

# SQLite reflects the 0001 constraint without a name; this convention names it for batch mode.
NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _global_unique_name() -> str:
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        return 'uq_clients_client_code'
    for uc in sa.inspect(bind).get_unique_constraints('clients'):
        if uc['column_names'] == ['client_code'] and uc.get('name'):
            return str(uc['name'])
    return 'clients_client_code_key'  # PostgreSQL default name


def upgrade() -> None:
    name = _global_unique_name()
    with op.batch_alter_table('clients', schema=None, naming_convention=NAMING) as batch_op:
        batch_op.drop_constraint(name, type_='unique')
        batch_op.create_unique_constraint('uq_clients_firm_code', ['firm_id', 'client_code'])


def downgrade() -> None:
    # Fails if two firms already share a client code (resolve that before downgrading).
    with op.batch_alter_table('clients', schema=None, naming_convention=NAMING) as batch_op:
        batch_op.drop_constraint('uq_clients_firm_code', type_='unique')
        batch_op.create_unique_constraint('uq_clients_client_code', ['client_code'])
