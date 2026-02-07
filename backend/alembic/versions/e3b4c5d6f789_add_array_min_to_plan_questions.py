"""add array_min to plan_questions

Revision ID: e3b4c5d6f789
Revises: d2a3b4c5e678
Create Date: 2026-02-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3b4c5d6f789'
down_revision: Union[str, None] = 'd2a3b4c5e678'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('plan_questions', sa.Column(
        'array_min', sa.Integer(), nullable=True,
        comment='array型の最低必須件数',
    ))


def downgrade() -> None:
    op.drop_column('plan_questions', 'array_min')
