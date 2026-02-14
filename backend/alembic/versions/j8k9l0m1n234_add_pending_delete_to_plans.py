"""add pending_delete to plans

Revision ID: j8k9l0m1n234
Revises: i7j8k9l0m123
Create Date: 2026-02-14 14:12:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j8k9l0m1n234'
down_revision: Union[str, None] = 'i7j8k9l0m123'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('plans', sa.Column('pending_delete', sa.Boolean(), nullable=False, server_default='0', comment='削除予約フラグ'))


def downgrade() -> None:
    op.drop_column('plans', 'pending_delete')
