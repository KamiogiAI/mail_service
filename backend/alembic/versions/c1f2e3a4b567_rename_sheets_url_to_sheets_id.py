"""rename sheets_url to sheets_id

Revision ID: c1f2e3a4b567
Revises: ba5a7bc54121
Create Date: 2026-02-02 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1f2e3a4b567'
down_revision: Union[str, None] = 'ba5a7bc54121'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('plans', 'sheets_url', new_column_name='sheets_id',
                    existing_type=sa.String(length=500),
                    existing_nullable=True,
                    comment='Google Sheets ID')


def downgrade() -> None:
    op.alter_column('plans', 'sheets_id', new_column_name='sheets_url',
                    existing_type=sa.String(length=500),
                    existing_nullable=True,
                    comment='Google Sheets URL')
