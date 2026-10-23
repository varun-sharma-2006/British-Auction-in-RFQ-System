"""users and roles

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.Enum('BUYER', 'SUPPLIER', name='user_role', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('supplier_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("role <> 'SUPPLIER' OR supplier_id IS NOT NULL", name='ck_user_supplier_has_company'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_users_supplier_id'), 'users', ['supplier_id'], unique=False)
    # batch mode so the same migration also runs on SQLite (no ALTER ... ADD CONSTRAINT there)
    with op.batch_alter_table('rfqs') as batch:
        batch.add_column(sa.Column('created_by_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_rfqs_created_by_id_users', 'users', ['created_by_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('rfqs') as batch:
        batch.drop_constraint('fk_rfqs_created_by_id_users', type_='foreignkey')
        batch.drop_column('created_by_id')
    op.drop_index(op.f('ix_users_supplier_id'), table_name='users')
    op.drop_table('users')
