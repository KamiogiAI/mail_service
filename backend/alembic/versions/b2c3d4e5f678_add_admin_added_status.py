"""add admin_added status to subscription_status enum

Revision ID: b2c3d4e5f678
Revises: a1b2c3d4e567
Create Date: 2026-02-05 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b2c3d4e5f678'
down_revision: Union[str, None] = 'a1b2c3d4e567'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MySQL: ENUM値を追加 (カラム定義を変更)
    op.execute("""
        ALTER TABLE subscriptions MODIFY COLUMN status
        ENUM('trialing','active','past_due','canceled','unpaid','incomplete','admin_added')
        NOT NULL DEFAULT 'active'
    """)


def downgrade() -> None:
    # admin_added を削除 (既存データがある場合は canceled に変換)
    op.execute("""
        UPDATE subscriptions SET status = 'canceled' WHERE status = 'admin_added'
    """)
    op.execute("""
        ALTER TABLE subscriptions MODIFY COLUMN status
        ENUM('trialing','active','past_due','canceled','unpaid','incomplete')
        NOT NULL DEFAULT 'active'
    """)
