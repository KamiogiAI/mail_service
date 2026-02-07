"""add trial_enabled to plans

Revision ID: d2a3b4c5e678
Revises: c1f2e3a4b567
Create Date: 2026-02-02 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2a3b4c5e678'
down_revision: Union[str, None] = 'c1f2e3a4b567'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('plans', sa.Column(
        'trial_enabled', sa.Boolean(), nullable=False,
        server_default=sa.text('1'),
        comment='初月無料トライアルを有効にする',
    ))


def downgrade() -> None:
    op.drop_column('plans', 'trial_enabled')
