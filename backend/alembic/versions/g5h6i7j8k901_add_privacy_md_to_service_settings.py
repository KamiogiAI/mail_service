"""add privacy_md to service_settings

Revision ID: g5h6i7j8k901
Revises: e3b4c5d6f789
Create Date: 2026-02-07 21:06:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g5h6i7j8k901'
down_revision = 'e3b4c5d6f789'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('service_settings', sa.Column('privacy_md', sa.Text(), nullable=True, comment='プライバシーポリシー'))


def downgrade() -> None:
    op.drop_column('service_settings', 'privacy_md')
