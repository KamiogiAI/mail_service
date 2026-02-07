"""add eligible_plan_ids to promotion_codes

Revision ID: a1b2c3d4e567
Revises: f4c5d6e7f890
Create Date: 2026-02-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e567'
down_revision: Union[str, None] = 'f4c5d6e7f890'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('promotion_codes', sa.Column('eligible_plan_ids', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('promotion_codes', 'eligible_plan_ids')
