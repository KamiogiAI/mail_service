"""add heartbeat retry cursor to progress_plan

Revision ID: i7j8k9l0m123
Revises: h6i7j8k9l012
Create Date: 2026-02-13

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i7j8k9l0m123'
down_revision = 'h6i7j8k9l012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # heartbeat_at: Watchdog用のハートビート
    op.add_column('progress_plan', sa.Column('heartbeat_at', sa.DateTime(), nullable=True))
    # retry_count: リトライ回数
    op.add_column('progress_plan', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))
    # max_retries: 最大リトライ回数
    op.add_column('progress_plan', sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'))
    # cursor: 途中再開用（最後に処理したアイテムID等）
    op.add_column('progress_plan', sa.Column('cursor', sa.String(255), nullable=True))
    # last_error: 最後のエラーメッセージ
    op.add_column('progress_plan', sa.Column('last_error', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('progress_plan', 'last_error')
    op.drop_column('progress_plan', 'cursor')
    op.drop_column('progress_plan', 'max_retries')
    op.drop_column('progress_plan', 'retry_count')
    op.drop_column('progress_plan', 'heartbeat_at')
