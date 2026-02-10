"""add stripe plan change tables and subscription scheduled fields

Revision ID: h6i7j8k9l012
Revises: g5h6i7j8k901
Create Date: 2026-02-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h6i7j8k9l012'
down_revision = 'g5h6i7j8k901'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # processed_stripe_events テーブル (webhook冪等性)
    op.create_table(
        'processed_stripe_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.String(255), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('processed_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_processed_stripe_events_event_id', 'processed_stripe_events', ['event_id'], unique=True)

    # subscription_plan_changes テーブル (プラン変更履歴)
    op.create_table(
        'subscription_plan_changes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=False),
        sa.Column('old_plan_id', sa.Integer(), nullable=True),
        sa.Column('new_plan_id', sa.Integer(), nullable=True),
        sa.Column('change_type', sa.String(20), nullable=False, comment='upgrade / downgrade / lateral'),
        sa.Column('effective_at', sa.DateTime(), nullable=True, comment='変更適用予定日時 (NULLなら即時適用済み)'),
        sa.Column('applied', sa.Boolean(), nullable=False, default=False, comment='適用済みフラグ'),
        sa.Column('stripe_event_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['old_plan_id'], ['plans.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['new_plan_id'], ['plans.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_subscription_plan_changes_subscription_id', 'subscription_plan_changes', ['subscription_id'])

    # subscriptions テーブルにダウングレード予約カラム追加
    op.add_column('subscriptions', sa.Column(
        'scheduled_plan_id', sa.Integer(), nullable=True,
        comment='ダウングレード予定プランID',
    ))
    op.add_column('subscriptions', sa.Column(
        'scheduled_change_at', sa.DateTime(), nullable=True,
        comment='プラン変更予定日時',
    ))
    op.create_foreign_key(
        'fk_subscriptions_scheduled_plan_id',
        'subscriptions', 'plans',
        ['scheduled_plan_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_subscriptions_scheduled_plan_id', 'subscriptions', type_='foreignkey')
    op.drop_column('subscriptions', 'scheduled_change_at')
    op.drop_column('subscriptions', 'scheduled_plan_id')
    op.drop_index('ix_subscription_plan_changes_subscription_id', 'subscription_plan_changes')
    op.drop_table('subscription_plan_changes')
    op.drop_index('ix_processed_stripe_events_event_id', 'processed_stripe_events')
    op.drop_table('processed_stripe_events')
