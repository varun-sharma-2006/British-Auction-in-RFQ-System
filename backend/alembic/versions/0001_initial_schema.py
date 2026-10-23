"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('rfqs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('reference_id', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('origin', sa.String(length=120), nullable=True),
    sa.Column('destination', sa.String(length=120), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('pickup_date', sa.Date(), nullable=False),
    sa.Column('bid_start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('bid_close_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('current_close_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('forced_close_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_british_auction', sa.Boolean(), nullable=False),
    sa.Column('trigger_window_minutes', sa.Integer(), nullable=True),
    sa.Column('extension_minutes', sa.Integer(), nullable=True),
    sa.Column('trigger_type', sa.Enum('BID_RECEIVED', 'ANY_RANK_CHANGE', 'L1_CHANGE', name='trigger_type', native_enum=False, create_constraint=True, length=32), nullable=True),
    sa.Column('status', sa.Enum('SCHEDULED', 'ACTIVE', 'CLOSED', 'FORCE_CLOSED', name='auction_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('extension_count', sa.Integer(), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('NOT is_british_auction OR (forced_close_at > bid_close_at AND trigger_window_minutes > 0 AND extension_minutes > 0 AND trigger_type IS NOT NULL)', name='ck_rfq_british_config_complete'),
    sa.CheckConstraint('bid_close_at > bid_start_at', name='ck_rfq_close_after_start'),
    sa.CheckConstraint('current_close_at >= bid_close_at AND current_close_at <= forced_close_at', name='ck_rfq_current_close_within_bounds'),
    sa.CheckConstraint('forced_close_at >= bid_close_at', name='ck_rfq_forced_not_before_close'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('reference_id')
    )
    op.create_index('ix_rfqs_status_close', 'rfqs', ['status', 'current_close_at'], unique=False)
    op.create_table('suppliers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('contact_email', sa.String(length=254), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('bids',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rfq_id', sa.Integer(), nullable=False),
    sa.Column('supplier_id', sa.Integer(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('carrier_name', sa.String(length=120), nullable=False),
    sa.Column('freight_charges', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('origin_charges', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('destination_charges', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('transit_time_days', sa.Integer(), nullable=False),
    sa.Column('quote_validity_date', sa.Date(), nullable=False),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('freight_charges >= 0 AND origin_charges >= 0 AND destination_charges >= 0', name='ck_bid_charges_non_negative'),
    sa.CheckConstraint('total_amount > 0', name='ck_bid_total_positive'),
    sa.CheckConstraint('transit_time_days > 0', name='ck_bid_transit_positive'),
    sa.ForeignKeyConstraint(['rfq_id'], ['rfqs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bids_rfq_supplier_created', 'bids', ['rfq_id', 'supplier_id', 'created_at'], unique=False)
    op.create_index('ix_bids_rfq_total', 'bids', ['rfq_id', 'total_amount'], unique=False)
    op.create_table('auction_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rfq_id', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.Enum('RFQ_CREATED', 'AUCTION_STARTED', 'BID_SUBMITTED', 'AUCTION_EXTENDED', 'EXTENSION_CAPPED', 'AUCTION_CLOSED', 'AUCTION_FORCE_CLOSED', name='event_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('supplier_id', sa.Integer(), nullable=True),
    sa.Column('bid_id', sa.Integer(), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('previous_close_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('new_close_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('details', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.ForeignKeyConstraint(['bid_id'], ['bids.id'], ),
    sa.ForeignKeyConstraint(['rfq_id'], ['rfqs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_events_rfq_id', 'auction_events', ['rfq_id', 'id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_events_rfq_id', table_name='auction_events')
    op.drop_table('auction_events')
    op.drop_index('ix_bids_rfq_total', table_name='bids')
    op.drop_index('ix_bids_rfq_supplier_created', table_name='bids')
    op.drop_table('bids')
    op.drop_table('suppliers')
    op.drop_index('ix_rfqs_status_close', table_name='rfqs')
    op.drop_table('rfqs')
