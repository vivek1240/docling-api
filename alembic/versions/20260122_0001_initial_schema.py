"""Initial schema with API keys, usage records, and Stripe events

Revision ID: 0001
Revises: 
Create Date: 2026-01-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('key_id', sa.String(50), nullable=False),
        sa.Column('key_hash', sa.String(64), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('tier', sa.String(20), nullable=False, server_default='starter'),
        sa.Column('credits', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('credits_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('documents_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pages_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('last_used', sa.DateTime(), nullable=True),
        sa.Column('stripe_customer_id', sa.String(100), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_api_keys_key_id', 'api_keys', ['key_id'], unique=True)
    op.create_index('ix_api_keys_key_hash', 'api_keys', ['key_hash'], unique=True)
    
    # Create usage_records table
    op.create_table(
        'usage_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('api_key_id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.String(50), nullable=False),
        sa.Column('endpoint', sa.String(100), nullable=False),
        sa.Column('documents', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('pages', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('credits', sa.Integer(), nullable=False),
        sa.Column('processing_time_ms', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='success'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_usage_records_request_id', 'usage_records', ['request_id'])
    op.create_index('idx_usage_api_key_created', 'usage_records', ['api_key_id', 'created_at'])
    
    # Create stripe_events table
    op.create_table(
        'stripe_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.String(100), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_stripe_events_event_id', 'stripe_events', ['event_id'], unique=True)


def downgrade() -> None:
    op.drop_table('stripe_events')
    op.drop_table('usage_records')
    op.drop_table('api_keys')
