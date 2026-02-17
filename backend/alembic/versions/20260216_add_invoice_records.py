"""add invoice_records table

Revision ID: 20260216_invoice
Revises: 
Create Date: 2026-02-16
"""
from alembic import op
import sqlalchemy as sa


revision = '20260216_invoice'
down_revision = 'j8k9l0m1n234'  # add_pending_delete_to_plans
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'invoice_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stripe_invoice_id', sa.String(255), nullable=False),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True),
        sa.Column('subscription_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('amount_paid', sa.Integer(), nullable=False, comment='実際の支払額（円）'),
        sa.Column('subtotal', sa.Integer(), nullable=True, comment='小計（割引前）'),
        sa.Column('discount_amount', sa.Integer(), nullable=True, comment='割引額'),
        sa.Column('promotion_code_id', sa.Integer(), nullable=True),
        sa.Column('coupon_id', sa.String(255), nullable=True, comment='Stripe Coupon ID'),
        sa.Column('period_start', sa.DateTime(), nullable=True),
        sa.Column('period_end', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='paid', comment='paid/void/uncollectible'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['promotion_code_id'], ['promotion_codes.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_invoice_records_stripe_invoice_id', 'invoice_records', ['stripe_invoice_id'], unique=True)
    op.create_index('ix_invoice_records_stripe_subscription_id', 'invoice_records', ['stripe_subscription_id'])
    op.create_index('ix_invoice_records_subscription_id', 'invoice_records', ['subscription_id'])
    op.create_index('ix_invoice_records_user_id', 'invoice_records', ['user_id'])


def downgrade():
    op.drop_index('ix_invoice_records_user_id', table_name='invoice_records')
    op.drop_index('ix_invoice_records_subscription_id', table_name='invoice_records')
    op.drop_index('ix_invoice_records_stripe_subscription_id', table_name='invoice_records')
    op.drop_index('ix_invoice_records_stripe_invoice_id', table_name='invoice_records')
    op.drop_table('invoice_records')
